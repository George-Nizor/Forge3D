from __future__ import annotations

import torch
from diso import DiffDMC


field = torch.ones((8, 8, 8), device="cuda")
field[2:6, 2:6, 2:6] = -1
vertices, faces = DiffDMC().to(field.device)(field)
print({"vertices": tuple(vertices.shape), "faces": tuple(faces.shape)})

