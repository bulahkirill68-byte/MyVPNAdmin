"""Public IPv4 discovery for a host installer; never reuses the build server's address."""
from collections import Counter
import ipaddress
import json
import subprocess

SERVICES = ('https://api.ipify.org', 'https://ipv4.icanhazip.com', 'https://ifconfig.co/ip')


def validate_ipv4(value):
    address = ipaddress.IPv4Address(str(value).strip())
    if not address.is_global:
        raise ValueError('Нужен публичный IPv4, а не LAN/loopback/служебный адрес')
    return str(address)


def fetch_address(url):
    return subprocess.run(['curl', '--noproxy', '*', '-4', '--proto', '=https', '--fail', '--silent',
                           '--show-error', '--connect-timeout', '4', '--max-time', '8', url],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def interface_addresses():
    result = subprocess.run(['ip', '-j', '-4', 'address', 'show', 'scope', 'global'],
                            capture_output=True, text=True, check=True, timeout=5)
    values = set()
    for interface in json.loads(result.stdout):
        for item in interface.get('addr_info', []):
            try:
                values.add(validate_ipv4(item.get('local', '')))
            except ValueError:
                pass
    return values


def detect_public_ip(fetch=fetch_address, interfaces=interface_addresses):
    votes = Counter()
    for url in SERVICES:
        try:
            address = validate_ipv4(fetch(url))
        except (ValueError, OSError, subprocess.SubprocessError):
            continue
        votes[address] += 1
        if votes[address] >= 2:
            return address
    try:
        local = set(interfaces())
    except (ValueError, OSError, subprocess.SubprocessError):
        local = set()
    if len(local) == 1 and (not votes or set(votes) == local):
        return validate_ipv4(next(iter(local)))
    raise ValueError('Не удалось однозначно определить IPv4. Запустите установщик с --ip ВАШ_IP')
