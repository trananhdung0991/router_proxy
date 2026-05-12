<template>
  <div class="panel-group-status">

    <!-- Rest of your existing template -->
    <div class="block">DHCP Clients ({{ list.length }})</div>

    <table v-if="list.length" class="table">
      <thead>
        <tr>
          <th>Hostname</th>
          <th>IP</th>
          <th>MAC</th>
          <th>Proxy Type</th>
          <th>Proxy</th>
          <th>Use proxy dns</th>
          <th>Bind IP to Mac</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in list" :key="c.ip">
          <td>{{ c.hostname || '-' }}</td>
          <td>{{ c.ip }}</td>
          <td>{{ c.mac }}</td>
          <td>
            <el-select
              v-model="proxyTypes[c.ip]"
              size="mini"
              placeholder="Select type"
              style="width: 100px"
              @focus="beginEdit(c)"
            >
              <el-option label="HTTP" value="HTTP"></el-option>
              <el-option label="SOCKS5" value="SOCKS5"></el-option>
            </el-select>
          </td>
          <td>
            <el-input
              v-model="proxies[c.ip]"
              size="mini"
              placeholder="proxy:port"
              style="width: 240px"
              clearable
              @focus="beginEdit(c)"
            />
          </td>
          <td style="text-align: center;">
            <el-checkbox
              v-model="remoteFakeDNS[c.ip]"
              @change="handleProxyDNSChange(c)"
              :disabled="!proxies[c.ip] || saving[c.ip]"
              size="mini"
            >
            </el-checkbox>
            <div style="font-size: 10px; color: #999; margin-top: 2px;">
              {{ remoteFakeDNS[c.ip] ? 'ON' : 'OFF' }}
            </div>
          </td>
          <td style="text-align: center;">
            <el-checkbox
              v-model="bindIPToMac[c.ip]"
              @change="handleBindIPToMacChange(c)"
              :disabled="saving[c.ip]"
              size="mini"
            >
            </el-checkbox>
            <div style="font-size: 10px; color: #999; margin-top: 2px;">
              {{ bindIPToMac[c.ip] ? 'ON' : 'OFF' }}
            </div>
          </td>
          <td>
            <el-button
              size="mini"
              type="primary"
              :loading="saving[c.ip] === true"
              @click="setProxy(c)"
            >Set</el-button>
            <el-button
              size="mini"
              :loading="saving[c.ip] === true"
              @click="clearProxy(c)"
            >Cancel</el-button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-else class="block">No DHCP clients</div>
  </div>
</template>

<script>
import { getClientList, setClientProxy, getClientProxies, bindIPToMac, getDHCPReservations } from '@/api/router-proxy/clientlist'

export default {
  name: 'ClientList',
  data() {
    return { 
      timer: null, 
      list: [], 
      proxies: {}, 
      proxyTypes: {},
      remoteFakeDNS: {}, 
      bindIPToMac: {},
      saving: {}, 
      editing: {}, 
      originals: {},
      originalTypes: {},
      savedProxies: {}, 
      passwall2Running: false,
      passwall2Nodes: []
    }
  },
  created() {
    this.loadData()
    this.timer = setInterval(() => {
      this.getList()
    }, 5000)
  },
  beforeDestroy() { 
    clearInterval(this.timer) 
  },
  deactivated() { 
    clearInterval(this.timer) 
  },
  methods: {
    async loadData() {
      // Load DHCP clients, saved proxies, and DHCP reservations
      await Promise.all([
        this.getList(),
        this.loadSavedProxies(),
        this.loadDHCPReservations()
      ])
      this.mergeProxyData()
    },

    getList() {
      return getClientList()
        .then(res => {
          console.log('DHCP clients response:', res)
          const payload = Array.isArray(res) ? res : (res && res.data)
          this.list = Array.isArray(payload) ? payload : []
          console.log('DHCP clients loaded:', this.list.length)
        })
        .catch(err => {
          console.error('DHCP fetch failed:', err)
          this.list = []
        })
    },

    loadSavedProxies() {
      return getClientProxies()
        .then(res => {
          console.log('=== Saved proxies API response ===')
          console.log('Full response:', res)
          console.log('Response type:', typeof res)
          console.log('Response status:', res?.status)
          console.log('Response data:', res?.data)
          console.log('Data type:', typeof res?.data)
          console.log('Data is array:', Array.isArray(res?.data))
          
          // Handle the response format: {"status": true, "data": [array], "count": 1}
          if (res && res.status === true && res.data) {
            // Convert array to object with IP as keys (what mergeProxyData expects)
            if (Array.isArray(res.data)) {
              console.log('Converting array to object with IP keys...')
              this.savedProxies = {}
              res.data.forEach(client => {
                console.log(`Adding client to savedProxies: ${client.ip}`, client)
                this.savedProxies[client.ip] = client
              })
              console.log('Final savedProxies object:', this.savedProxies)
            } else {
              console.log('Data is already an object, using directly')
              this.savedProxies = res.data
            }
          } else {
            console.log('Invalid response format or status false')
            this.savedProxies = {}
          }
          
          console.log('=== End saved proxies processing ===')
        })
        .catch(err => {
          console.error('Failed to load saved proxies:', err)
          this.savedProxies = {}
        })
    },

    loadDHCPReservations() {
      console.log('=== Loading DHCP reservations ===')
      return getDHCPReservations()
        .then(res => {
          console.log('=== DHCP reservations API response ===')
          console.log('Full response:', res)
          console.log('Response status:', res?.status)
          console.log('Response bindings:', res?.bindings)
          
          if (res && res.status === true && res.bindings) {
            console.log('Loading DHCP IP-MAC bindings:', res.bindings)
            console.log('Current bindIPToMac state before update:', JSON.stringify(this.bindIPToMac))
            
            // res.bindings is an object like { "192.168.1.100": true, "192.168.1.101": true }
            Object.keys(res.bindings).forEach(ip => {
              if (res.bindings[ip]) {
                console.log(`Setting bindIPToMac[${ip}] = true`)
                this.$set(this.bindIPToMac, ip, true)
              }
            })
            console.log('Updated bindIPToMac state after update:', JSON.stringify(this.bindIPToMac))
          } else {
            console.log('No DHCP reservations found or invalid response')
            console.log('Response details:', {
              exists: !!res,
              status: res?.status,
              hasBindings: !!res?.bindings,
              bindingsType: typeof res?.bindings
            })
          }
          
          console.log('=== End DHCP reservations processing ===')
        })
        .catch(err => {
          console.error('Failed to load DHCP reservations:', err)
          console.error('Error details:', err.response || err.message)
        })
    },

    mergeProxyData() {
      console.log('=== Merging proxy data ===')
      console.log('DHCP clients count:', this.list.length)
      console.log('Saved proxies count:', Object.keys(this.savedProxies).length)
      console.log('Saved proxies keys:', Object.keys(this.savedProxies))
      
      // Initialize proxy fields for all clients
      this.list.forEach(c => {
        const ip = c.ip
        console.log(`Processing client: ${ip}`)
        
        // Initialize reactive properties if not exists
        if (!(ip in this.proxies)) {
          this.$set(this.proxies, ip, '')
          this.$set(this.proxyTypes, ip, 'HTTP')
          this.$set(this.remoteFakeDNS, ip, false)
          // Don't reset bindIPToMac if it was already set by loadDHCPReservations
          if (!(ip in this.bindIPToMac)) {
            this.$set(this.bindIPToMac, ip, false)
          }
          this.$set(this.originals, ip, '')
          this.$set(this.originalTypes, ip, 'HTTP')
          this.$set(this.editing, ip, false)
          this.$set(this.saving, ip, false)
          console.log(`Initialized reactive properties for ${ip}`)
        }
        
        // Load saved proxy data if available and not currently editing
        if (this.savedProxies[ip] && !this.editing[ip]) {
          const savedProxy = this.savedProxies[ip].proxy || ''
          const savedFakeDNS = this.savedProxies[ip].remote_fakedns || false
          const savedProxyType = this.savedProxies[ip].proxy_type || 'HTTP'
          
          console.log(`Loading saved data for ${ip}:`, {
            proxy: savedProxy,
            proxy_type: savedProxyType,
            remote_fakedns: savedFakeDNS
          })
          
          this.$set(this.proxies, ip, savedProxy)
          this.$set(this.proxyTypes, ip, savedProxyType)
          this.$set(this.remoteFakeDNS, ip, savedFakeDNS)
          this.$set(this.originals, ip, savedProxy)
          this.$set(this.originalTypes, ip, savedProxyType)
          
          console.log(`Applied saved settings for ${ip}: proxy="${savedProxy}", type=${savedProxyType}, fakedns=${savedFakeDNS}`)
        } else {
          console.log(`No saved data found for ${ip} or currently editing`)
        }
      })
      
      console.log('=== Final proxy states ===')
      console.log('Proxies:', this.proxies)
      console.log('RemoteFakeDNS:', this.remoteFakeDNS)
      console.log('=== End merge ===')
    },

    beginEdit(c) {
      const ip = c.ip
      if (!this.editing[ip]) {
        this.$set(this.originals, ip, this.proxies[ip] || '')
        this.$set(this.originalTypes, ip, this.proxyTypes[ip] || 'HTTP')
        this.$set(this.editing, ip, true)
        console.log(`Started editing ${ip}`)
      }
    },

    handleProxyDNSChange(c) {
      const ip = c.ip
      
      // Check if proxy is set
      if (!this.proxies[ip] || this.proxies[ip].trim() === '') {
        this.$set(this.remoteFakeDNS, ip, false)
        this.$message({
          message: 'Please set a proxy first before enabling proxy DNS',
          type: 'warning'
        })
        return
      }

    },

    handleBindIPToMacChange(c) {
      const ip = c.ip
      const mac = c.mac
      const hostname = c.hostname || ''
      const bindEnabled = this.bindIPToMac[ip]
      
      console.log(`IP-to-MAC binding for ${ip} (${mac}): ${bindEnabled}`)
      
      // Set saving state
      this.$set(this.saving, ip, true)
      
      // Call the API to bind/unbind IP to MAC
      bindIPToMac({
        ip: ip,
        mac: mac,
        hostname: hostname,
        bind: bindEnabled
      })
        .then((res) => {
          console.log('Bind IP to MAC response:', res)
          
          if (res && res.status === true) {
            if (bindEnabled) {
              this.$message({
                message: `IP ${ip} successfully bound to MAC ${mac}`,
                type: 'success'
              })
            } else {
              this.$message({
                message: `IP ${ip} binding to MAC ${mac} removed`,
                type: 'success'
              })
            }
          } else {
            // API call failed, revert the checkbox
            this.$set(this.bindIPToMac, ip, !bindEnabled)
            
            const errorMsg = (res && res.error) || 'Failed to update IP-MAC binding'
            this.$message({
              message: errorMsg,
              type: 'error'
            })
          }
        })
        .catch(err => {
          console.error('Bind IP to MAC failed:', err)
          
          // API call failed, revert the checkbox
          this.$set(this.bindIPToMac, ip, !bindEnabled)
          
          let errorMsg = 'Failed to update IP-MAC binding'
          
          if (err.response && err.response.data) {
            errorMsg = err.response.data.error || err.response.data.message || errorMsg
          } else if (err.message) {
            errorMsg = err.message
          }
          
          this.$message({
            message: errorMsg,
            type: 'error'
          })
        })
        .finally(() => {
          this.$set(this.saving, ip, false)
        })
    },

    setProxy(c) {
      const ip = c.ip
      const proxy_url = (this.proxies[ip] || '').trim()
      const proxy_type = this.proxyTypes[ip] || 'HTTP'
      const use_proxy_dns = this.remoteFakeDNS[ip] || false
      
      console.log(`Setting proxy for ${ip}: "${proxy_url}", type: ${proxy_type}, fakedns: ${use_proxy_dns}`)
      
      this.$set(this.saving, ip, true)
      
      setClientProxy({ 
        ip: c.ip, 
        mac: c.mac, 
        hostname: c.hostname, 
        proxy: proxy_url,
        proxy_type: proxy_type,
        remote_fakedns: use_proxy_dns
      })
        .then((res) => {
          console.log('Set proxy response:', res)
          
          if (res && res.status === true) {
            this.$message({
              message: 'Configuration saved successfully',
              type: 'success'
            })
            // Update saved state
            this.$set(this.originals, ip, proxy_url)
            this.$set(this.originalTypes, ip, proxy_type)
            this.$set(this.editing, ip, false)
            
            // Update saved proxies cache immediately
            if (!this.savedProxies[ip]) {
              this.$set(this.savedProxies, ip, {})
            }
            this.$set(this.savedProxies[ip], 'ip', ip)
            this.$set(this.savedProxies[ip], 'proxy', proxy_url)
            this.$set(this.savedProxies[ip], 'proxy_type', proxy_type)
            this.$set(this.savedProxies[ip], 'remote_fakedns', use_proxy_dns)
            this.$set(this.savedProxies[ip], 'hostname', c.hostname || '')
            this.$set(this.savedProxies[ip], 'mac', c.mac || '')
            
            console.log('Updated savedProxies cache:', this.savedProxies[ip])
          } else {
            const errorMsg = (res && res.error) || 'Save failed'
            this.$message({
              message: errorMsg,
              type: 'error'
            })
          }
        })
        .catch(err => {
          console.error('Set proxy failed:', err)
          let errorMsg = 'Failed to save configuration'
          
          if (err.response && err.response.data) {
            errorMsg = err.response.data.error || err.response.data.message || errorMsg
          } else if (err.message) {
            errorMsg = err.message
          }
          
          this.$message({
            message: errorMsg,
            type: 'error'
          })
        })
        .finally(() => {
          this.$set(this.saving, ip, false)
        })
    },

    clearProxy(c) {
      const ip = c.ip
      console.log(`Clearing proxy for ${ip}`)
      
      this.$set(this.proxies, ip, '')
      this.$set(this.proxyTypes, ip, 'HTTP')
      this.$set(this.remoteFakeDNS, ip, false)
      this.$set(this.saving, ip, true)
      
      setClientProxy({ 
        ip: c.ip, 
        mac: c.mac, 
        hostname: c.hostname, 
        proxy: '',
        proxy_type: 'HTTP',
        remote_fakedns: false
      })
        .then((res) => {
          console.log('Clear proxy response:', res)
          
          if (res && res.status === true) {
            this.$message({
              message: 'Configuration cleared successfully',
              type: 'success'
            })
            this.$set(this.originals, ip, '')
            this.$set(this.originalTypes, ip, 'HTTP')
            this.$set(this.editing, ip, false)
            
            // Remove from saved proxies cache
            if (this.savedProxies[ip]) {
              this.$delete(this.savedProxies, ip)
              console.log(`Removed ${ip} from savedProxies cache`)
            }
          } else {
            const errorMsg = (res && res.error) || 'Clear failed'
            this.$message({
              message: errorMsg,
              type: 'error'
            })
          }
        })
        .catch(err => {
          console.error('Clear proxy failed:', err)
          let errorMsg = 'Failed to clear configuration'
          
          if (err.response && err.response.data) {
            errorMsg = err.response.data.error || err.response.data.message || errorMsg
          } else if (err.message) {
            errorMsg = err.message
          }
          
          this.$message({
            message: errorMsg,
            type: 'error'
          })
        })
        .finally(() => {
          this.$set(this.saving, ip, false)
        })
    },
  }
}
</script>

<style lang="scss">
.table { 
  width: 100%; 
  border-collapse: collapse; 
}

.table th, .table td { 
  text-align: left; 
  padding: 8px 10px; 
  border-bottom: 1px solid #eee; 
}

.table th:nth-child(6), .table td:nth-child(6),
.table th:nth-child(7), .table td:nth-child(7) {
  text-align: center;
  width: 100px;
}

.el-checkbox {
  margin: 0;
}
</style>