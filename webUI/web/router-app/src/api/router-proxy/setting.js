import xrequest from '@/utils/xrequest'

/**
 * Get current router IP configuration
 * @returns {Promise} Router configuration data
 */
export function getRouterIP() {
  return xrequest({
    url: '/api/openwrt/router/current-config',
    method: 'get'
  })
}

/**
 * Set router IP configuration
 * @param {Object} data - Router configuration data
 * @param {string} data.newIP - New router IP address
 * @param {string} data.netmask - Subnet mask
 * @param {string} data.currentIP - Current router IP (optional)
 * @param {string} data.interface - Network interface (optional, defaults to 'lan')
 * @param {string} data.dhcpStart - DHCP range start IP (optional)
 * @param {string} data.dhcpEnd - DHCP range end IP (optional)
 * @returns {Promise} Response from router IP change operation
 */
export function setRouterIP(data) {
  return xrequest({
    url: '/api/openwrt/router/change-ip',
    method: 'post',
    data
  })
}

/**
 * Test router IP availability
 * @param {Object} data - Test configuration
 * @param {string} data.testIP - IP address to test
 * @param {string} data.interface - Network interface (optional)
 * @returns {Promise} Test results
 */
export function testRouterIP(data) {
  return xrequest({
    url: '/api/openwrt/router/test-ip',
    method: 'post',
    data
  })
}