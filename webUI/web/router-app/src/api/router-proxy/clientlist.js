import xrequest from '@/utils/xrequest'

// Get DHCP clients from router
export function getClientList() {
  return xrequest({
    url: '/dhcp_clients',
    method: 'get',
    timeout: 15000
  })
}

// Get saved client proxy configurations
export function getClients() {
  return xrequest({
    url: '/clients',
    method: 'get',
    timeout: 15000
  })
}

// Alias for getClients - this is what StatusPanel.vue is looking for
export function getClientProxies() {
  return getClients()
}

// Set client proxy configuration
export function setClientProxy(data) {
  return xrequest({
    url: '/client_proxy',
    method: 'post',
    data: {
      ip: data.ip,
      hostname: data.hostname || '',
      proxy: data.proxy || '',
      proxy_type: data.proxy_type || 'HTTP',
      remote_fakedns: data.remote_fakedns || false
    },
    timeout: 15000
  })
}

// Get specific client proxy configuration
export function getClientProxy(ip) {
  return xrequest({
    url: `/client_proxy/${ip}`,
    method: 'get',
    timeout: 15000
  })
}

// Test proxy connection
export function testProxyConnection(proxyUrl) {
  return xrequest({
    url: '/test_proxy',
    method: 'post',
    data: {
      proxy_url: proxyUrl
    },
    timeout: 15000
  })
}

// Get Passwall2 status
export function getPasswall2Status() {
  return xrequest({
    url: '/passwall2/status',
    method: 'get',
    timeout: 15000
  })
}

// Get Passwall2 nodes
export function getPasswall2Nodes() {
  return xrequest({
    url: '/passwall2/nodes',
    method: 'get',
    timeout: 15000
  })
}

// Remove client proxy
export function removeClientProxy(ip) {
  return xrequest({
    url: `/client_proxy/${ip}`,
    method: 'delete',
    timeout: 15000
  })
}

// Bind IP to MAC address (DHCP reservation)
export function bindIPToMac(data) {
  return xrequest({
    url: '/client/bind_ip_mac',
    method: 'post',
    data: {
      ip: data.ip,
      mac: data.mac,
      hostname: data.hostname || '',
      bind: data.bind
    },
    timeout: 15000
  })
}

// Get DHCP reservations
export function getDHCPReservations() {
  return xrequest({
    url: '/client/dhcp_reservations',
    method: 'get',
    timeout: 10000
  })
}
