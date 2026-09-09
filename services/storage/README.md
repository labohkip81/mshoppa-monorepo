# Storage boundary

Reserved for the standalone Django storage service. The initial local adapter now lives in `services/core/apps/catalog/images.py`: tenant-authorized product uploads, input validation/normalization, local `.local/media/` storage and signed image reads. No unrestricted media directory is exposed. Private-document uploads, object-storage adapters and deployment of this independent service remain future work.
