# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Runtime symmetric INT4 weight-only quantization for Intel XPU.

Full-precision checkpoint weights are loaded layer-wise through vLLM's online
processing path, quantized to GGML Q4_0 (128-value groups), and retained in the
layouts consumed by the XPU W4A16 kernels.
"""

import ctypes
import importlib
import os
from typing import Any

import torch
from torch.nn import Module

import vllm.envs as envs
from vllm.logger import init_logger
from vllm.model_executor.layers.fused_moe import (
    FusedMoEConfig,
    FusedMoEQuantConfig,
    RoutedExperts,
    SharedExperts,
)
from vllm.model_executor.layers.fused_moe.unquantized_fused_moe_method import (
    UnquantizedFusedMoEMethod,
)
from vllm.model_executor.layers.linear import (
    LinearBase,
    LinearMethodBase,
    UnquantizedLinearMethod,
)
from vllm.model_executor.layers.quantization import QuantizationMethods
from vllm.model_executor.layers.quantization._sym_int4_esimd import (
    _ESIMD_INT4_ADAPTER,
    _int4_esimd_disabled,
)
from vllm.model_executor.layers.quantization.base_config import (
    QuantizationConfig,
    QuantizeMethodBase,
)
from vllm.model_executor.layers.quantization.online.moe_base import (
    OnlineMoEMethodBase,
)
from vllm.model_executor.model_loader.reload.layerwise import (
    get_layerwise_info,
    initialize_online_processing,
)
from vllm.model_executor.parameter import ModelWeightParameter
from vllm.model_executor.utils import replace_parameter
from vllm.platforms import current_platform

logger = init_logger(__name__)


def _p7_noop(*args, **kwargs):  # phase7: logger.info_once breaks torch.compile (dynamo gb0291)
    return None

QK4_GROUP_SIZE = 128
QK4_PACK_FACTOR = 8

_QLIB_CACHE: tuple[str, ctypes.CDLL] | None = None
_ESIMD_Q40_AVAILABLE: bool | None = None


def _get_quant_lib() -> ctypes.CDLL:
    """Load the CPU Q4_0 fallback library once per configured path."""
    global _QLIB_CACHE

    path = envs.VLLM_QUANTIZE_Q40_LIB
    if _QLIB_CACHE is not None and _QLIB_CACHE[0] == path:
        return _QLIB_CACHE[1]

    try:
        clib = ctypes.CDLL(path)
    except OSError as exc:
        raise RuntimeError(
            "Runtime sym_int4 could not load its CPU Q4_0 fallback library "
            f"at {path!r}. Install the library or set VLLM_QUANTIZE_Q40_LIB."
        ) from exc

    quantize = clib.quantize_q4_0_to_qweight_and_scale
    quantize.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    quantize.restype = ctypes.c_size_t
    _QLIB_CACHE = (path, clib)
    return clib


def ggml_quantize_tensor(
    weight: torch.Tensor,
    out_qweight: torch.Tensor,
    out_scale: torch.Tensor,
    out_features: int,
    in_features: int,
    block_size: int = QK4_GROUP_SIZE,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Quantize one contiguous CPU FP32 matrix to row-major GGML Q4_0."""
    if weight.device.type != "cpu" or weight.dtype != torch.float32:
        raise ValueError("weight must be a CPU float32 tensor")
    if weight.shape != (out_features, in_features) or not weight.is_contiguous():
        raise ValueError("weight must be contiguous with the declared shape")
    if in_features % block_size != 0:
        raise ValueError(f"in_features must be divisible by {block_size}")
    if out_qweight.shape != (out_features, in_features // QK4_PACK_FACTOR):
        raise ValueError("out_qweight has an invalid shape")
    if out_scale.shape != (out_features, in_features // block_size):
        raise ValueError("out_scale has an invalid shape")
    if out_qweight.dtype != torch.int32 or out_qweight.device.type != "cpu":
        raise ValueError("out_qweight must be a CPU int32 tensor")
    if out_scale.dtype != torch.float16 or out_scale.device.type != "cpu":
        raise ValueError("out_scale must be a CPU float16 tensor")
    if not out_qweight.is_contiguous() or not out_scale.is_contiguous():
        raise ValueError("Q4_0 output tensors must be contiguous")

    quantize = _get_quant_lib().quantize_q4_0_to_qweight_and_scale
    quantize(
        ctypes.cast(weight.data_ptr(), ctypes.POINTER(ctypes.c_float)),
        ctypes.cast(out_qweight.data_ptr(), ctypes.POINTER(ctypes.c_int32)),
        ctypes.cast(out_scale.data_ptr(), ctypes.POINTER(ctypes.c_uint16)),
        out_features,
        in_features,
        block_size,
    )
    return out_qweight, out_scale


def _esimd_q40_available() -> bool:
    global _ESIMD_Q40_AVAILABLE
    if _ESIMD_Q40_AVAILABLE is not None:
        return _ESIMD_Q40_AVAILABLE

    try:
        importlib.import_module("custom_esimd_kernels_vllm.q4_0_quant_ops")
        _ = torch.ops.custom_esimd_kernels_vllm.q4_0_quantize
    except (AttributeError, ImportError, OSError) as exc:
        logger.debug("XPU Q4_0 runtime quantizer is unavailable: %s", exc)
        _ESIMD_Q40_AVAILABLE = False
    else:
        _ESIMD_Q40_AVAILABLE = True
    return _ESIMD_Q40_AVAILABLE


def _use_xpu_esimd_q40() -> bool:
    return (
        envs.VLLM_SYM_INT4_WEIGHT_QUANT_BACKEND == "xpu_esimd"
        and _esimd_q40_available()
    )


def _runtime_quantize_q4_0(
    weight: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Quantize a 2D BF16/FP16 tensor with the configured backend."""
    if weight.ndim != 2 or weight.dtype not in (torch.bfloat16, torch.float16):
        raise ValueError("Q4_0 input must be a 2D BF16/FP16 tensor")
    if not weight.is_contiguous():
        weight = weight.contiguous()

    rows, in_features = weight.shape
    if in_features % QK4_GROUP_SIZE != 0:
        raise ValueError(
            f"Q4_0 input width must be divisible by {QK4_GROUP_SIZE}, got {in_features}"
        )

    backend = envs.VLLM_SYM_INT4_WEIGHT_QUANT_BACKEND
    if weight.device.type == "xpu" and _use_xpu_esimd_q40():
        logger.info_once(
            "sym_int4 runtime quantization is using the Torch 2.12 ESIMD Q4_0 kernel.",
            scope="local",
        )
        qweight = torch.empty(
            rows,
            in_features // QK4_PACK_FACTOR,
            dtype=torch.int32,
            device=weight.device,
        )
        scales = torch.empty(
            rows,
            in_features // QK4_GROUP_SIZE,
            dtype=torch.float16,
            device=weight.device,
        )
        torch.ops.custom_esimd_kernels_vllm.q4_0_quantize(weight, qweight, scales)
        return qweight, scales

    if weight.device.type == "xpu" and backend == "xpu_esimd":
        logger.warning_once(
            "VLLM_SYM_INT4_WEIGHT_QUANT_BACKEND=xpu_esimd was requested, "
            "but custom_esimd_kernels_vllm.q4_0_quant_ops is unavailable; "
            "falling back to CPU Q4_0 quantization."
        )
    else:
        logger.info_once(
            "sym_int4 runtime weight quantization is using the CPU Q4_0 backend.",
            scope="local",
        )

    weight_cpu = weight.to(device="cpu", dtype=torch.float32).contiguous()
    # The legacy C packer ORs the first nibble into each output word, so the
    # destination must start at zero rather than contain uninitialized data.
    qweight_cpu = torch.zeros(
        rows, in_features // QK4_PACK_FACTOR, dtype=torch.int32, device="cpu"
    )
    scales_cpu = torch.empty(
        rows, in_features // QK4_GROUP_SIZE, dtype=torch.float16, device="cpu"
    )
    ggml_quantize_tensor(
        weight_cpu,
        qweight_cpu,
        scales_cpu,
        rows,
        in_features,
    )
    return (
        qweight_cpu.to(weight.device),
        scales_cpu.to(weight.device),
    )


class SymInt4Config(QuantizationConfig):
    """Runtime GGML Q4_0 quantization configuration."""

    def __init__(self) -> None:
        super().__init__()
        if not current_platform.is_xpu():
            raise ValueError("sym_int4 runtime quantization is only supported on XPU")

    @classmethod
    def get_name(cls) -> QuantizationMethods:
        return "sym_int4"

    @classmethod
    def get_supported_act_dtypes(cls) -> list[torch.dtype]:
        return [torch.bfloat16, torch.float16]

    @classmethod
    def get_min_capability(cls) -> int:
        return -1

    @staticmethod
    def get_config_filenames() -> list[str]:
        return []

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SymInt4Config":
        return cls()

    def get_quant_method(
        self, layer: torch.nn.Module, prefix: str
    ) -> QuantizeMethodBase | None:
        if isinstance(layer, LinearBase):
            if self._is_layer_skipped(prefix):
                return UnquantizedLinearMethod()
            return SymInt4LinearMethod(self)
        if isinstance(layer, RoutedExperts):
            if self._is_layer_skipped(prefix):
                return UnquantizedFusedMoEMethod(layer.moe_config)
            return SymInt4MoEMethod(self, layer.moe_config)
        return None

    @staticmethod
    def _is_layer_skipped(prefix: str) -> bool:
        excluded = ("visual", "vision", "vpm", "resampler", "shared_expert")
        included = ("vision_experts",)
        return any(name in prefix for name in excluded) and not any(
            name in prefix for name in included
        )


class SymInt4LinearMethod(LinearMethodBase):
    """Runtime Q4_0 linear method using the XPU oneDNN W4A16 GEMM."""

    uses_meta_device = True
    is_sym_int4 = True

    def __init__(self, quant_config: SymInt4Config):
        self.quant_config = quant_config

    def create_weights(
        self,
        layer: torch.nn.Module,
        input_size_per_partition: int,
        output_partition_sizes: list[int],
        input_size: int,
        output_size: int,
        params_dtype: torch.dtype,
        **extra_weight_attrs,
    ) -> None:
        del input_size, output_size
        output_size_per_partition = sum(output_partition_sizes)
        weight_loader = extra_weight_attrs.get("weight_loader")

        layer.logical_widths = output_partition_sizes
        layer.input_size_per_partition = input_size_per_partition
        layer.output_size_per_partition = output_size_per_partition
        layer.orig_dtype = params_dtype

        weight = ModelWeightParameter(
            data=torch.empty(
                output_size_per_partition,
                input_size_per_partition,
                dtype=params_dtype,
                device="meta",
            ),
            input_dim=1,
            output_dim=0,
            weight_loader=weight_loader,
        )
        layer.register_parameter("weight", weight)
        initialize_online_processing(layer)

    def process_weights_after_loading(self, layer: Module) -> None:
        if getattr(layer, "_already_called_process_weights_after_loading", False):
            return

        _require_complete_layerwise_load(layer, ("weight",))
        weight = layer.weight.detach()
        _, in_features = weight.shape
        padded_in_features = (
            (in_features + QK4_GROUP_SIZE - 1) // QK4_GROUP_SIZE
        ) * QK4_GROUP_SIZE
        if padded_in_features != in_features:
            weight = torch.nn.functional.pad(
                weight, (0, padded_in_features - in_features)
            ).contiguous()

        qweight, scales = _runtime_quantize_q4_0(weight)
        _register_linear_int4_layouts(layer, qweight, scales)
        replace_parameter(layer, "weight", None)
        layer._int4_in_features = in_features
        layer._int4_in_features_padded = padded_in_features
        layer._already_called_process_weights_after_loading = True

    def apply(
        self,
        layer: torch.nn.Module,
        x: torch.Tensor,
        bias: torch.Tensor | None = None,
    ) -> torch.Tensor:
        x_2d = x.reshape(-1, x.shape[-1])
        padded_in_features = layer._int4_in_features_padded
        if x_2d.shape[-1] != padded_in_features:
            if x_2d.shape[-1] > padded_in_features:
                raise ValueError(
                    f"sym_int4 input width {x_2d.shape[-1]} exceeds quantized "
                    f"weight width {padded_in_features}"
                )
            x_2d = torch.nn.functional.pad(
                x_2d, (0, padded_in_features - x_2d.shape[-1])
            )

        allow_batch_esimd = (
            getattr(layer, "_sym_int4_allow_batch_esimd", False)
            and os.environ.get("DISABLE_ESIMD_INT4_GEMM", "0") != "1"
            and os.environ.get("DISABLE_GEMMA4_INT4_BATCH_ESIMD", "0") != "1"
        )
        esimd_output = None
        weight_esimd = getattr(layer, "weight_esimd", None)
        if (
            x_2d.shape[0] == 1
            and not _int4_esimd_disabled()
            and isinstance(weight_esimd, torch.Tensor)
            and x_2d.device.type == "xpu"
            and x_2d.dtype == torch.float16
        ):
            buffers = getattr(layer, "_int4_esimd_output_buffers", None)
            if buffers is None:
                buffers = {}
                layer._int4_esimd_output_buffers = buffers
            esimd_output = buffers.get(1)
            expected_shape = (1, weight_esimd.shape[0])
            if (
                esimd_output is None
                or tuple(esimd_output.shape) != expected_shape
                or esimd_output.device != x_2d.device
            ):
                esimd_output = torch.empty(
                    expected_shape,
                    dtype=torch.float16,
                    device=x_2d.device,
                )
                buffers[1] = esimd_output
        output = _ESIMD_INT4_ADAPTER.try_linear(
            x_2d,
            weight_esimd,
            getattr(layer, "scale_esimd", None),
            bias=bias,
            output=esimd_output,
            allow_batch=allow_batch_esimd,
        )
        if output is not None:
            _p7_noop(
                "sym_int4 linear execution is using the guarded ESIMD path.",
                scope="local",
            )
            return output.reshape(x.shape[:-1] + (output.shape[-1],))

        _p7_noop(
            "sym_int4 linear execution is using the XPU W4A16 kernel.",
            scope="local",
        )
        output = torch.ops._xpu_C.int4_gemm_w4a16(
            x_2d,
            layer.qweight,
            bias,
            layer.scales,
            layer.qzeros,
            QK4_GROUP_SIZE,
            None,
        )
        return output.reshape(x.shape[:-1] + (layer.qweight.shape[-1],))


def _require_complete_layerwise_load(
    layer: Module, parameter_names: tuple[str, ...]
) -> None:
    """Reject missing/partial online loads instead of quantizing garbage."""
    for name in parameter_names:
        parameter = getattr(layer, name, None)
        if parameter is None:
            raise RuntimeError(f"sym_int4 expected parameter {name!r} before loading")
        if parameter.device.type == "meta":
            raise RuntimeError(
                f"sym_int4 parameter {name!r} was not materialized from a "
                "checkpoint weight"
            )

    info = get_layerwise_info(layer)
    if (
        info.can_load()
        and info.load_numel_total is not None
        and info.load_numel < info.load_numel_total
    ):
        raise RuntimeError(
            "sym_int4 requires a complete checkpoint load before runtime "
            f"quantization (loaded {info.load_numel} of "
            f"{info.load_numel_total} elements)"
        )


def _register_linear_int4_layouts(
    layer: Module,
    qweight: torch.Tensor,
    scales: torch.Tensor,
) -> None:
    """Install oneDNN layouts without duplicating the packed weight storage."""
    if qweight.ndim != 2 or scales.ndim != 2:
        raise ValueError("linear Q4_0 weights and scales must be 2D")
    if qweight.shape[0] != scales.shape[0]:
        raise ValueError("Q4_0 weight and scale row counts must match")

    # ESIMD consumes the quantizer's N-major bytes directly. Keep aliases so
    # enabling the fast path never duplicates the packed weight or scale.
    replace_parameter(layer, "weight_esimd", qweight.view(torch.uint8))
    replace_parameter(layer, "scale_esimd", scales)

    # The transpose view has logical [K/8, N] shape and K-packed stride 1,
    # while sharing the row-major [N, K/8] storage emitted by the quantizer.
    replace_parameter(layer, "qweight", qweight.t())
    replace_parameter(layer, "scales", scales.t().contiguous())
    replace_parameter(
        layer,
        "qzeros",
        torch.tensor([8], dtype=torch.int8, device=qweight.device),
    )


class SymInt4MoEMethod(OnlineMoEMethodBase):
    """Runtime Q4_0 method using vLLM's current modular WNA16 MoE path."""

    is_sym_int4 = True

    def __init__(self, quant_config: SymInt4Config, moe: FusedMoEConfig):
        super().__init__(moe)
        self.quant_config = quant_config
        self._xpu_fused_moe_impl = None

    @property
    def supports_eplb(self) -> bool:
        return False

    def create_weights(
        self,
        layer: torch.nn.Module,
        num_experts: int,
        hidden_size: int,
        intermediate_size_per_partition: int,
        params_dtype: torch.dtype,
        **extra_weight_attrs,
    ) -> None:
        if not self.moe.is_act_and_mul:
            raise NotImplementedError("sym_int4 MoE requires an act-and-mul activation")
        if hidden_size % QK4_GROUP_SIZE != 0:
            raise ValueError(
                f"sym_int4 MoE hidden size must be divisible by "
                f"{QK4_GROUP_SIZE}, got {hidden_size}"
            )
        super().create_weights(
            layer,
            num_experts,
            hidden_size,
            intermediate_size_per_partition,
            params_dtype,
            **extra_weight_attrs,
        )

    def process_weights_after_loading(self, layer: RoutedExperts) -> None:
        if getattr(layer, "_already_called_process_weights_after_loading", False):
            return

        parameter_names = ["w13_weight", "w2_weight"]
        if self.moe.has_bias:
            parameter_names.extend(("w13_bias", "w2_bias"))
        _require_complete_layerwise_load(layer, tuple(parameter_names))

        w13, w13_scales, padded_intermediate = _quantize_moe_w13(
            layer.w13_weight.detach()
        )
        replace_parameter(layer, "w13_weight", w13)
        replace_parameter(layer, "w13_scales", w13_scales)
        if self.moe.has_bias:
            replace_parameter(
                layer,
                "w13_bias",
                _pad_moe_w13_bias(layer.w13_bias.detach(), padded_intermediate),
            )

        w2, w2_scales, w2_padded_intermediate = _quantize_moe_w2(
            layer.w2_weight.detach()
        )
        if w2_padded_intermediate != padded_intermediate:
            raise RuntimeError("sym_int4 MoE produced inconsistent padded shapes")
        replace_parameter(layer, "w2_weight", w2)
        replace_parameter(layer, "w2_scales", w2_scales)
        layer._int4_intermediate_size_padded = padded_intermediate

        self._setup_moe_kernel(layer)
        layer._already_called_process_weights_after_loading = True

    def _setup_moe_kernel(self, layer: RoutedExperts) -> None:
        from vllm.model_executor.layers.fused_moe.experts.xpu_moe import (
            XPUExpertsWNA16,
        )
        from vllm.model_executor.layers.fused_moe.oracle.int_wna16 import (
            make_wna16_moe_kernel,
            select_wna16_moe_backend,
        )
        from vllm.model_executor.layers.quantization.utils.quant_utils import (
            kInt4Static,
        )

        self.moe_quant_config = self.get_fused_moe_quant_config(layer)
        backend, experts_cls = select_wna16_moe_backend(self.moe, kInt4Static)
        if experts_cls is not XPUExpertsWNA16:
            raise RuntimeError(
                "sym_int4 MoE requires the XPU WNA16 backend for its packed "
                f"weight layout, but selected {experts_cls.__name__}"
            )
        self.moe_kernel = make_wna16_moe_kernel(
            moe_quant_config=self.moe_quant_config,
            moe_config=self.moe,
            experts_cls=experts_cls,
            backend=backend,
            routing_tables=layer._expert_routing_tables(),
        )

    def get_fused_moe_quant_config(self, layer: RoutedExperts) -> FusedMoEQuantConfig:
        from vllm.model_executor.layers.fused_moe.oracle.int_wna16 import (
            make_wna16_moe_quant_config,
        )

        return make_wna16_moe_quant_config(
            w1_scale=layer.w13_scales,
            w2_scale=layer.w2_scales,
            group_size=QK4_GROUP_SIZE,
            num_bits=4,
            w1_bias=getattr(layer, "w13_bias", None),
            w2_bias=getattr(layer, "w2_bias", None),
            gemm1_clamp_limit=getattr(layer, "swiglu_limit", None),
            gemm1_alpha=getattr(layer, "swiglu_alpha", None),
            gemm1_beta=getattr(layer, "swiglu_beta", None),
        )

    def get_xpu_fused_moe_impl(
        self, layer: RoutedExperts, experts_per_token: int
    ) -> Any:
        """Return the canonical XPU implementation and its signed-s4 weights."""
        from vllm_xpu_kernels.fused_moe_interface import XpuFusedMoe

        if self._xpu_fused_moe_impl is None:
            self._xpu_fused_moe_impl = XpuFusedMoe(
                w13=layer.w13_weight,
                w13_scales=layer.w13_scales,
                w13_bias=getattr(layer, "w13_bias", None),
                w2=layer.w2_weight,
                w2_scales=layer.w2_scales,
                w2_bias=getattr(layer, "w2_bias", None),
                n_experts_per_token=experts_per_token,
                activation=layer.activation.value,
                num_experts=layer.local_num_experts,
                ep_rank=self.moe.ep_rank,
                ep_size=self.moe.ep_size,
                expert_map=layer.expert_map,
                gemm1_clamp_limit=getattr(layer, "swiglu_limit", None),
            )
        return self._xpu_fused_moe_impl

    def apply(
        self,
        layer: RoutedExperts,
        x: torch.Tensor,
        topk_weights: torch.Tensor,
        topk_ids: torch.Tensor,
        shared_experts: SharedExperts | None,
        shared_experts_input: torch.Tensor | None,
    ) -> torch.Tensor:
        if shared_experts is None and shared_experts_input is None:
            impl = self.get_xpu_fused_moe_impl(layer, topk_ids.size(-1))
            output = torch.empty_like(x)
            impl.apply(
                output=output,
                hidden_states=x,
                topk_weights=topk_weights,
                topk_ids=topk_ids,
            )
            return output

        return super().apply(
            layer,
            x,
            topk_weights,
            topk_ids,
            shared_experts,
            shared_experts_input,
        )


def _padded_intermediate_size(intermediate_size: int) -> int:
    return ((intermediate_size + QK4_GROUP_SIZE - 1) // QK4_GROUP_SIZE) * QK4_GROUP_SIZE


def _pad_moe_w13_bias(bias: torch.Tensor, padded_intermediate: int) -> torch.Tensor:
    """Pad gate/up bias halves to match a padded fused w13 weight."""
    if bias.ndim != 2 or bias.shape[1] % 2 != 0:
        raise ValueError("sym_int4 w13 bias must have shape [E, 2I]")
    num_experts, twice_intermediate = bias.shape
    intermediate = twice_intermediate // 2
    if intermediate > padded_intermediate:
        raise ValueError("sym_int4 w13 bias exceeds the padded intermediate size")
    if intermediate == padded_intermediate:
        return bias
    bias = bias.view(num_experts, 2, intermediate)
    return (
        torch.nn.functional.pad(bias, (0, padded_intermediate - intermediate))
        .reshape(num_experts, 2 * padded_intermediate)
        .contiguous()
    )


def _quantize_moe_w13(
    weight: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Quantize gate/up experts to compact [E, 2I, H/2] uint8."""
    if weight.ndim != 3 or weight.shape[1] % 2 != 0:
        raise ValueError("sym_int4 w13 weight must have shape [E, 2I, H]")
    num_experts, twice_intermediate, hidden_size = weight.shape
    if hidden_size % QK4_GROUP_SIZE != 0:
        raise ValueError(
            f"sym_int4 MoE hidden size must be divisible by "
            f"{QK4_GROUP_SIZE}, got {hidden_size}"
        )

    intermediate_size = twice_intermediate // 2
    padded_intermediate = _padded_intermediate_size(intermediate_size)
    if padded_intermediate != intermediate_size:
        weight = weight.view(num_experts, 2, intermediate_size, hidden_size)
        weight = torch.nn.functional.pad(
            weight, (0, 0, 0, padded_intermediate - intermediate_size)
        )
        weight = weight.reshape(
            num_experts, 2 * padded_intermediate, hidden_size
        ).contiguous()

    qweight, scales = _runtime_quantize_q4_0(weight.view(-1, hidden_size))
    qweight = qweight.view(
        num_experts, 2 * padded_intermediate, hidden_size // QK4_PACK_FACTOR
    ).view(torch.uint8)
    scales = scales.view(
        num_experts, 2 * padded_intermediate, hidden_size // QK4_GROUP_SIZE
    )
    return qweight, scales, padded_intermediate


def _quantize_moe_w2(
    weight: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, int]:
    """Quantize down experts to compact [E, H, I/2] uint8."""
    if weight.ndim != 3:
        raise ValueError("sym_int4 w2 weight must have shape [E, H, I]")
    num_experts, hidden_size, intermediate_size = weight.shape
    padded_intermediate = _padded_intermediate_size(intermediate_size)
    if padded_intermediate != intermediate_size:
        weight = torch.nn.functional.pad(
            weight, (0, padded_intermediate - intermediate_size)
        ).contiguous()

    qweight, scales = _runtime_quantize_q4_0(weight.view(-1, padded_intermediate))
    qweight = qweight.view(
        num_experts,
        hidden_size,
        padded_intermediate // QK4_PACK_FACTOR,
    ).view(torch.uint8)
    scales = scales.view(
        num_experts,
        hidden_size,
        padded_intermediate // QK4_GROUP_SIZE,
    )
    return qweight, scales, padded_intermediate
