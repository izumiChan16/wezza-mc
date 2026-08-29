# Secrets

`./mcctl init` creates the local secret files used by Compose:

- `rcon_password.txt`: internal RCON authentication.
- `restic_password.txt`: encryption password for the optional restic repository.
- `aws_credentials`: S3-compatible credentials; edit this only when remote backup is enabled.

The real files are ignored by Git. Never publish them to GitHub Pages.
