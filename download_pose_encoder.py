"""Download the correct pose_encoder.pth from ModelScope."""
import os
import sys

weights_dir = r"D:\git\AINews\AINews\third_party\echomimic_v2\pretrained_weights"
target = os.path.join(weights_dir, "pose_encoder.pth")
backup = target + ".bad"

# Check current (corrupt) file
if os.path.exists(target):
    size_mb = os.path.getsize(target) / 1024 / 1024
    print(f"Current pose_encoder.pth: {size_mb:.1f} MB (expected ~5-20 MB, this is corrupt)")
    os.rename(target, backup)
    print(f"Renamed corrupt file to: {backup}")

print("Downloading from ModelScope...")
try:
    from modelscope.hub.file_download import model_file_download
    path = model_file_download(
        "BadToBest/EchoMimicV2",
        "pose_encoder.pth",
        local_dir=weights_dir,
        cache_dir=os.path.join(weights_dir, ".cache"),
    )
    new_size = os.path.getsize(path) / 1024 / 1024
    print(f"Downloaded: {path} ({new_size:.1f} MB)")

    # Verify it's not corrupted by loading it
    import torch
    d = torch.load(path, map_location="cpu", weights_only=False)
    total_numel = sum(v.numel() for v in d.values())
    # Check storage is not bloated
    storages = {}
    for v in d.values():
        ptr = v.storage().data_ptr()
        storages[ptr] = v.storage().size()
    storage_total = sum(storages.values())
    print(f"Keys: {len(d)}, Total params: {total_numel:,}")
    print(f"Storage elements: {storage_total:,}  (should be close to {total_numel:,})")
    if storage_total > total_numel * 10:
        print("ERROR: Still corrupted! Storage is much larger than params.")
        sys.exit(1)
    else:
        print("OK: pose_encoder.pth looks valid!")
        if os.path.exists(backup):
            os.remove(backup)
            print("Removed backup of corrupt file.")

except Exception as e:
    print(f"ERROR: {e}")
    # Restore backup if download failed
    if os.path.exists(backup) and not os.path.exists(target):
        os.rename(backup, target)
        print("Restored backup.")
    sys.exit(1)
