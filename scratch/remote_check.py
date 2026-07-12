import sys
import os
import paramiko

def run_remote_check():
    sys.stdout.reconfigure(encoding='utf-8')
    host = "84.247.179.163"
    port = 2951
    user = "mwhebaco"
    key_path = r"c:\Users\UTD\Desktop\MWHEBA ERP\deployments\elbaraka\ssh_key"
    
    print(f"Connecting to {user}@{host}:{port} using key {key_path}...")
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # Load key
        key = paramiko.RSAKey.from_private_key_file(key_path, password="MedooAlnems2008")
        ssh.connect(host, port=port, username=user, pkey=key)
        print("Connected successfully!\n")
        
        commands = [
            "mysql -u mwhebaco_elbaraka_erp -p'LWv)pZE.7sc[xakJ' mwhebaco_elbaraka_erp -e \"SELECT \`key\`, \`value\` FROM core_systemsetting;\"",
        ]
        
        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='ignore')
            err = stderr.read().decode('utf-8', errors='ignore')
            if out:
                print(f"Output:\n{out}")
            if err:
                print(f"Error:\n{err}")
            print("-" * 50)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    run_remote_check()
