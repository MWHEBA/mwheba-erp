# Deployment Notes - MEGroup

## Client Info
- **Name**: MEGroup
- **Domain**: system.megroup-eg.com
- **Created**: 2026-07-02

## Server
- **IP**: 84.247.179.163
- **Port**: 2951
- **User**: megroupe
- **Path**: /home/megroupe/megroup_erp
- **SSH Key**: `deployments/megroup/ssh_key`

## Database
- **Database**: megroupe_megroup_erp
- **User**: megroupe_megroup_erp

## Email
- **Address**: info@megroup-eg.com
- **SMTP**: mail.mwheba.co.uk:587

## Superuser
- **Username**: admin
- **Email**: info@megroup-eg.com

## Notes
No additional notes

## Checklist
- [ ] Create database on server
- [ ] Create email account
- [ ] Create symlink for static: `ln -s /home/megroupe/megroup_erp/staticfiles /home/megroupe/system.megroup-eg.com/static`
- [ ] Create symlink for media: `ln -s /home/megroupe/megroup_erp/media /home/megroupe/system.megroup-eg.com/media`
- [ ] Upload files (first deploy)
- [ ] Run migrations
- [ ] Create superuser
- [ ] Test the system
