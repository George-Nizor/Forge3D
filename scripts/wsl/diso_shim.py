"""Inference-only permissive replacement for TripoSG's optional `diso` package.

It implements the tiny `DiffDMC` surface used by TripoSG with scikit-image.
This is not differentiable and is intentionally limited to inference.
"""

from __future__ import annotations

import numpy as np
import torch
from skimage.measure import marching_cubes


class DiffDMC(torch.nn.Module):
    def __init__(self, dtype: torch.dtype = torch.float32) -> None:
        super().__init__()
        self.dtype = dtype

    def forward(
        self,
        sdf: torch.Tensor,
        deform=None,
        return_quads: bool = False,
        normalize: bool = False,
    ):
        if deform is not None:
            raise ValueError("The Forge3D inference shim does not support deformation.")
        if return_quads:
            raise ValueError("The Forge3D inference shim outputs triangles only.")

        field = sdf.detach().float().cpu().numpy()
        finite = field[np.isfinite(field)]
        outside = max(float(finite.max()) if finite.size else 1.0, 1.0)
        field = np.nan_to_num(field, nan=outside, posinf=outside, neginf=-outside)
        vertices, faces, _normals, _values = marching_cubes(
            field,
            level=0.0,
            allow_degenerate=False,
        )
        if normalize:
            extent = np.maximum(np.asarray(field.shape, dtype=np.float32) - 1.0, 1.0)
            vertices = vertices / extent

        return (
            torch.from_numpy(np.asarray(vertices, dtype=np.float32)).to(sdf.device),
            torch.from_numpy(np.asarray(faces, dtype=np.int64)).to(sdf.device),
        )

