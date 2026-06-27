import torch

d = torch.load(
    r'D:\git\AINews\AINews\third_party\echomimic_v2\pretrained_weights\pose_encoder.pth',
    map_location='cpu',
    weights_only=False
)
print("Keys:", list(d.keys()))
for k, v in d.items():
    storage_size = v.storage().size()
    view_size = v.numel()
    print(f"{k}: shape={list(v.shape)}, numel={view_size}, storage={storage_size}, mean={v.float().mean():.4f}, std={v.float().std():.4f}")
print("\nTotal storage across all tensors:")
storages = {}
for k, v in d.items():
    ptr = v.storage().data_ptr()
    storages[ptr] = v.storage().size()
total = sum(storages.values())
print(f"  Unique storages: {len(storages)}, total elements: {total}, total MB (fp32)={total*4/1024/1024:.1f}")
