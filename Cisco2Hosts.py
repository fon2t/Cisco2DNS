import logging
import sys
import datetime
import paramiko
import re
import os
import subprocess
import yaml
import time

# Load YAML configuration file
def load_config(yaml_file):
    with open(yaml_file, 'r') as file:
        return yaml.safe_load(file)

# Initialize logging
def initialize_logging(log_level):
    level = logging.DEBUG if log_level == 'DEBUG' else logging.INFO
    logging.basicConfig(stream=sys.stderr, level=level)

#############################
# Connect to device using ssh
#############################
def ssh_connect(hostname, username, password, port):
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname, username=username, password=password, timeout=10, port=port)
        return ssh_client
    except paramiko.AuthenticationException:
        logging.error("Authentication failed. Please check your credentials.")
        return None
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error connecting to {hostname}: {e}")
        return None

def retrieve_dhcp_pool_config(ssh_client):
    try:
        logging.info("SSH: Retrieving DHCP configuration")
        stdin, stdout, stderr = ssh_client.exec_command("show running-config | include ip dhcp pool | host")
        dhcp_config = stdout.read().decode("utf-8")
        logging.info("SSH: Retrieved DHCP configuration")
        return dhcp_config
    except paramiko.SSHException as e:
        logging.error(f"SSH: Error retrieving DHCP pool configuration: {e}")
        return None

def read_existing_host_file(existing_file):
    try:
        with open(existing_file, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return ""

def convert_to_host_file(dhcp_config, existing_content, dnsdomain):
    lines = dhcp_config.split('\n')
    in_dhcp_pool = False
    host_entries = []
    unix_hosts = ""

    for line in lines:
        line = line.strip()
        pool_match = re.match(r"\s*ip dhcp pool (.+)$", line)
        if pool_match:
            in_dhcp_pool = True
            pool_name = pool_match.group(1).lower()
        elif in_dhcp_pool and re.match(r"\s*host ([^\s]+) ([^\s]+)", line):
            entry = re.match(r"\s*host ([^\s]+) ([^\s]+)", line)
            ip_address, netmask = entry.group(1), entry.group(2)
            host_entries.append((ip_address, pool_name + dnsdomain))
        else:
            in_dhcp_pool = False

    sorted_entries = sorted(host_entries, key=lambda x: tuple(map(int, x[0].split('.')[1:])))

    # Create file header
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Auto created host file \n# Generated from switch dhcp configuration \n# Generated on {now} \n"
    
    unix_hosts = header + existing_content + "\n".join([f"{ip} {hostname}" for ip, hostname in sorted_entries])

    return unix_hosts

def write_to_file(file_path, content):
    with open(file_path, 'w', newline=os.linesep) as file:
        file.write(content)

def execute_unix_commands(chown_cmd, chgrp_cmd, restart_cmd):
    try:
        subprocess.run(chown_cmd, check=True, shell=True)
        subprocess.run(chgrp_cmd, check=True, shell=True)
        subprocess.run(restart_cmd, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing Unix commands: {e}")

#############################
# Fortinet Interactive Shell
#############################
def send_command(shell, command):
    shell.send(command + '\n')
    time.sleep(1)  # Give some time for the command to be executed
    output = shell.recv(10000).decode('utf-8')  # Adjust buffer size as needed
    logging.info(f"Executed command: {command}\nOutput: {output}")
    return output

def configure_fortinet_dns(shell, base_name, dnsdomain, ttl, dns_entries):
    logging.info("Starting Fortinet DNS configuration")

    # Enter configuration mode
    send_command(shell, "config system dns-database")
    send_command(shell, f"edit \"{base_name}\"")
    send_command(shell, f"set domain \"{dnsdomain}\"")
    send_command(shell, f"set ttl {ttl}")
    send_command(shell, "config dns-entry")

    # Add DNS entries
    for idx, (hostname, ip) in enumerate(dns_entries, start=1):
        send_command(shell, f"edit {idx}")
        send_command(shell, f"set hostname \"{hostname}\"")
        send_command(shell, f"set ip {ip}")
        send_command(shell, "next")
    
    # Exit the DNS configuration
    send_command(shell, "end")
    logging.info("Fortinet DNS configuration complete")

def write_dns_to_fortinet(fortinet_host, fortinet_user, fortinet_pass, base_name, dnsdomain, ttl, dns_entries):
    logging.info("SSH: Connecting to Fortinet Firewall")

    # Connect to Fortinet Firewall via SSH
    ssh_client = ssh_connect(fortinet_host, fortinet_user, fortinet_pass, 22)  # Assuming default SSH port is 22
    
    if ssh_client:
        try:
            # Open an interactive shell
            shell = ssh_client.invoke_shell()
            time.sleep(1)  # Wait for the shell to be ready

            # Perform DNS configuration
            configure_fortinet_dns(shell, base_name, dnsdomain, ttl, dns_entries)

        except paramiko.SSHException as e:
            logging.error(f"SSH: Error writing DNS entries to Fortinet Firewall: {e}")
        finally:
            ssh_client.close()

#############################
# Main Routine
#############################
def main():
    # Load the configuration
    config = load_config("config.yaml")
    initialize_logging(config['logging']['level'])

    # SSH into the Cisco device
    ssh_client = ssh_connect(config['ssh']['hostname'], config['ssh']['username'], config['ssh']['password'], config['ssh']['port'])
    
    if ssh_client:
        dhcp_config = retrieve_dhcp_pool_config(ssh_client)
        base_host_file = read_existing_host_file(config['files']['existing_host_file'])

        if dhcp_config:
            host_file = convert_to_host_file(dhcp_config, base_host_file, config['dns']['domain'])
            logging.info("FUNCTION: Converted Cisco configuration to Unix style host file:\n")
            logging.debug(host_file)

            write_to_file(config['files']['output_file'], host_file)
            logging.info(f"FILEIO: Host file written to: {config['files']['output_file']}")
        
            # Execute Unix commands
            execute_unix_commands(config['commands']['chown'], config['commands']['chgrp'], config['commands']['restart'])

        ssh_client.close()
    
    # DNS entries for Fortinet Firewall (replace with actual parsed data)
    dns_entries = [("server", "172.26.20.40"), ("printer", "172.26.20.41")]

    # Write DNS entries to Fortinet Firewall
    write_dns_to_fortinet(
        config['fortinet']['hostname'], 
        config['fortinet']['username'], 
        config['fortinet']['password'], 
        config['fortinet']['base_name'],  # Using base_name from config
        config['dns']['domain'],          # Using domain from config
        config['fortinet']['ttl'],        # Using TTL from config
        dns_entries
    )

if __name__ == "__main__":
    main()
