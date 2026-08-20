import os
import sys
import time
from pathlib import Path
import paramiko

# Fix Windows console encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

def run_remote_reset():
    # Credentials from deployments/test/.env
    host = "84.247.179.163"
    port = 2951
    user = "mwhebaco"
    password = "MedooAlnems2008"
    key_path = Path("deployments/test/ssh_key")
    key_passphrase = "MedooAlnems2008"
    remote_path = "/home/mwhebaco/test_erp"
    remote_python = "/home/mwhebaco/virtualenv/test_erp/3.11/bin/python"

    print(f"Connecting to {host}:{port} as {user}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    pkey = None
    if key_path.exists():
        try:
            pkey = paramiko.RSAKey.from_private_key_file(str(key_path), password=key_passphrase)
        except Exception as e:
            print(f"SSH key load note: {e}")

    try:
        if pkey:
            ssh.connect(hostname=host, port=port, username=user, pkey=pkey, timeout=30)
        else:
            ssh.connect(hostname=host, port=port, username=user, password=password, timeout=30)
        print("Connected successfully!")
    except Exception as e:
        print(f"Retrying with password: {e}")
        ssh.connect(hostname=host, port=port, username=user, password=password, timeout=30)

    # 1. Upload the updated setup_development.py
    sftp = ssh.open_sftp()
    local_setup = Path("setup_development.py")
    remote_setup = f"{remote_path}/setup_development.py"
    print(f"Uploading {local_setup} to {remote_setup}...")
    sftp.put(str(local_setup), remote_setup)
    print("Uploaded setup_development.py successfully!")
    sftp.close()

    # 2. Run setup_development.py --auto remotely inside the test_erp directory
    cmd = f"cd {remote_path} && {remote_python} setup_development.py --auto"
    print(f"\nExecuting remote command:\n{cmd}\n{'='*60}")

    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
    
    while True:
        line = stdout.readline()
        if not line:
            break
        print(line, end='', flush=True)

    exit_status = stdout.channel.recv_exit_status()
    print(f"\n{'='*60}\nCommand exit status: {exit_status}")

    # 3. Restart application
    print("\nRestarting web application...")
    restart_cmd = f"/usr/sbin/cloudlinux-selector restart --json --interpreter python --app-root test_erp"
    stdin, stdout, stderr = ssh.exec_command(restart_cmd, timeout=60)
    restart_exit = stdout.channel.recv_exit_status()
    restart_out = stdout.read().decode('utf-8', errors='replace').strip()
    restart_err = stderr.read().decode('utf-8', errors='replace').strip()
    print(f"Restart exit code: {restart_exit}")
    if restart_out:
        print(f"Output: {restart_out}")
    if restart_err:
        print(f"Error: {restart_err}")

    # Also touch passenger_wsgi.py to ensure Passenger picks up changes
    ssh.exec_command(f"touch {remote_path}/passenger_wsgi.py")
    print("Touched passenger_wsgi.py for reload.")

    ssh.close()
    print("\nRemote operation completed!")

if __name__ == "__main__":
    run_remote_reset()
