#! /nix/store/xkz38nlafxlb2jry727hg5l64iln9c05-bash-5.3p9/bin/bash -e
# Helper command to manipulate both the IPv4 and IPv6 tables.
ip46tables() {
  iptables -w "$@"
  ip6tables -w "$@"

}


# Flush the old firewall rules.  !!! Ideally, updating the
# firewall would be atomic.  Apparently that's possible
# with iptables-restore.
ip46tables -D INPUT -j nixos-fw 2> /dev/null || true
for chain in nixos-fw nixos-fw-accept nixos-fw-log-refuse nixos-fw-refuse; do
  ip46tables -F "$chain" 2> /dev/null || true
  ip46tables -X "$chain" 2> /dev/null || true
done


# The "nixos-fw-accept" chain just accepts packets.
ip46tables -N nixos-fw-accept
ip46tables -A nixos-fw-accept -j ACCEPT


# The "nixos-fw-refuse" chain rejects or drops packets.
ip46tables -N nixos-fw-refuse

ip46tables -A nixos-fw-refuse -j DROP



# The "nixos-fw-log-refuse" chain performs logging, then
# jumps to the "nixos-fw-refuse" chain.
ip46tables -N nixos-fw-log-refuse



ip46tables -A nixos-fw-log-refuse -m pkttype ! --pkt-type unicast -j nixos-fw-refuse

ip46tables -A nixos-fw-log-refuse -j nixos-fw-refuse


# The "nixos-fw" chain does the actual work.
ip46tables -N nixos-fw

# Clean up rpfilter rules
ip46tables -t mangle -D PREROUTING -j nixos-fw-rpfilter 2> /dev/null || true
ip46tables -t mangle -F nixos-fw-rpfilter 2> /dev/null || true
ip46tables -t mangle -X nixos-fw-rpfilter 2> /dev/null || true

# Perform a reverse-path test to refuse spoofers
# For now, we just drop, as the mangle table doesn't have a log-refuse yet
ip46tables -t mangle -N nixos-fw-rpfilter 2> /dev/null || true
ip46tables -t mangle -A nixos-fw-rpfilter -m rpfilter --validmark  -j RETURN

# Allows this host to act as a DHCP4 client without first having to use APIPA
iptables -t mangle -A nixos-fw-rpfilter -p udp --sport 67 --dport 68 -j RETURN

# Allows this host to act as a DHCPv4 server
iptables -t mangle -A nixos-fw-rpfilter -s 0.0.0.0 -d 255.255.255.255 -p udp --sport 68 --dport 67 -j RETURN


ip46tables -t mangle -A nixos-fw-rpfilter -j DROP

ip46tables -t mangle -A PREROUTING -j nixos-fw-rpfilter


# Accept all traffic on the trusted interfaces.
ip46tables -A nixos-fw -i lo -j nixos-fw-accept


# Accept packets from established or related connections.
ip46tables -A nixos-fw -m conntrack --ctstate ESTABLISHED,RELATED -j nixos-fw-accept

# Accept connections to the allowed TCP ports.


# Accept connections to the allowed TCP port ranges.


# Accept packets on the allowed UDP ports.


# Accept packets on the allowed UDP port ranges.


# Optionally respond to ICMPv4 pings.
iptables -w -A nixos-fw -p icmp --icmp-type echo-request -j nixos-fw-accept


# Accept all ICMPv6 messages except redirects and node
# information queries (type 139).  See RFC 4890, section
# 4.4.
ip6tables -A nixos-fw -p icmpv6 --icmpv6-type redirect -j DROP
ip6tables -A nixos-fw -p icmpv6 --icmpv6-type 139 -j DROP
ip6tables -A nixos-fw -p icmpv6 -j nixos-fw-accept

# Allow this host to act as a DHCPv6 client
ip6tables -A nixos-fw -d fe80::/64 -p udp --dport 546 -j nixos-fw-accept


# Helper command to manipulate both the IPv4 and IPv6 tables.
ip46tables() {
  iptables -w "$@"
  ip6tables -w "$@"

}

ip46tables -w -t nat -D PREROUTING -j nixos-nat-pre 2>/dev/null|| true
ip46tables -w -t nat -F nixos-nat-pre 2>/dev/null || true
ip46tables -w -t nat -X nixos-nat-pre 2>/dev/null || true
ip46tables -w -t nat -D POSTROUTING -j nixos-nat-post 2>/dev/null || true
ip46tables -w -t nat -F nixos-nat-post 2>/dev/null || true
ip46tables -w -t nat -X nixos-nat-post 2>/dev/null || true
ip46tables -w -t nat -D OUTPUT -j nixos-nat-out 2>/dev/null || true
ip46tables -w -t nat -F nixos-nat-out 2>/dev/null || true
ip46tables -w -t nat -X nixos-nat-out 2>/dev/null || true
ip46tables -w -t filter -D FORWARD -j nixos-filter-forward 2>/dev/null || true
ip46tables -w -t filter -F nixos-filter-forward 2>/dev/null || true
ip46tables -w -t filter -X nixos-filter-forward 2>/dev/null || true




# Reject/drop everything else.
ip46tables -A nixos-fw -j nixos-fw-log-refuse


# Enable the firewall.
ip46tables -A INPUT -j nixos-fw

