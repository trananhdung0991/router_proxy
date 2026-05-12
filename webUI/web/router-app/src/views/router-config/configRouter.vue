<template>
  <div class="app-container">
    <!-- Router IP Configuration -->
    <el-card class="box-card">
      <div slot="header" class="clearfix">
        <span class="card-title">🌐 Router IP Configuration</span>
      </div>
      
      <el-form
        ref="routerForm"
        :model="routerConfig"
        :rules="rules"
        label-width="120px"
        label-position="left"
      >
        <!-- Router IP Configuration -->
        <el-form-item label="Router IP" prop="routerIP">
          <el-input
            v-model="routerConfig.routerIP"
            placeholder="Enter router IP address (e.g., 192.168.2.1)"
            style="width: 400px"
          >
            <template slot="append">
              <el-button 
                type="text" 
                icon="el-icon-refresh" 
                @click="loadCurrentConfig"
                :loading="loadingCurrent"
                title="Load current IP"
              ></el-button>
            </template>
          </el-input>
          <div v-if="currentRouterIP && currentRouterIP !== routerConfig.routerIP" class="current-ip-hint">
            <small>Current IP: <el-tag size="mini" type="info">{{ currentRouterIP }}</el-tag></small>
          </div>
        </el-form-item>

        <!-- Subnet Mask Configuration -->
        <el-form-item label="Netmask" prop="netmask">
          <el-input
            v-model="routerConfig.netmask"
            placeholder="Enter subnet mask (e.g., 255.255.255.0)"
            style="width: 400px"
          >
          </el-input>
        </el-form-item>

        <!-- DHCP Range Configuration -->
        <el-form-item label="DHCP Start" prop="dhcpStart">
          <el-input
            v-model="routerConfig.dhcpStart"
            placeholder="DHCP range start (e.g., 192.168.2.100)"
            style="width: 400px"
          >
          </el-input>
        </el-form-item>

        <el-form-item label="DHCP End" prop="dhcpEnd">
          <el-input
            v-model="routerConfig.dhcpEnd"
            placeholder="DHCP range end (e.g., 192.168.2.200)"
            style="width: 400px"
          >
          </el-input>
        </el-form-item>

        <!-- Action Buttons -->
        <el-form-item>
          <el-button
            type="primary"
            :loading="saveLoading"
            @click="changeRouterIP"
            :disabled="!routerConfig.routerIP || !isValidIP(routerConfig.routerIP)"
          >
            <i class="el-icon-switch-button"></i>
            Change Router IP
          </el-button>
        </el-form-item>

        <!-- end of form actions -->
        </el-form>
    </el-card>

    <!-- System Controls Card -->
    <el-card class="box-card" style="margin-top: 16px;">
      <div slot="header" class="clearfix">
        <span class="card-title">⚙️ System Controls</span>
      </div>
      <div style="padding: 10px 0;">
        <el-button type="danger" @click="confirmReboot" :loading="rebootLoading">
          <i class="el-icon-refresh-left"></i>
          Reboot Router
        </el-button>
        <el-button type="warning" style="margin-left:12px" @click="confirmRestart" :loading="restartLoading">
          <i class="el-icon-refresh"></i>
          Restart Service
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script>
import {
  setRouterIP,
  getRouterIP,
  testRouterIP
} from '@/api/router-proxy/setting'
import { rebootSystem, restartService } from '@/api/router-proxy/api'

export default {
  name: 'ConfigRouter',
  data() {
    // IP address validation
    const validateIP = (rule, value, callback) => {
      if (!value) {
        return callback(new Error('IP address is required'))
      }
      if (!this.isValidIP(value)) {
        return callback(new Error('Please enter a valid IP address'))
      }
      callback()
    }

    // Netmask validation
    const validateNetmask = (rule, value, callback) => {
      if (!value) {
        return callback(new Error('Subnet mask is required'))
      }
      if (!this.isValidIP(value)) {
        return callback(new Error('Please enter a valid subnet mask'))
      }
      callback()
    }

    return {
      loadingCurrent: false,
      saveLoading: false,
      testLoading: false,
      rebootLoading: false,
      restartLoading: false,
      connectionStatus: null,
      connectionMessage: 'Not tested',
      
      // Current router configuration
      currentRouterIP: '',
      currentInterface: '',
      currentNetmask: '',
      currentDHCPStart: '',
      currentDHCPEnd: '',
      
      // Router IP configuration
      routerConfig: {
        routerIP: '',
        interface: 'lan',
        netmask: '255.255.255.0',
        dhcpStart: '',
        dhcpEnd: ''
      },
      
      // Form validation rules
      rules: {
        routerIP: [
          { validator: validateIP, trigger: 'blur' }
        ],
        interface: [
          { required: true, message: 'Network interface is required', trigger: 'change' }
        ],
        netmask: [
          { validator: validateNetmask, trigger: 'blur' }
        ],
        dhcpStart: [
          { validator: validateIP, trigger: 'blur' }
        ],
        dhcpEnd: [
          { validator: validateIP, trigger: 'blur' }
        ]
      }
    }
  },
  
  watch: {
    // Watch for changes in Router IP and auto-update DHCP range
    'routerConfig.routerIP': {
      handler(newIP, oldIP) {
        if (newIP && this.isValidIP(newIP) && newIP !== oldIP) {
          this.updateDHCPRange(newIP)
        }
      },
      immediate: false
    }
  },
  
  mounted() {
    this.loadCurrentConfig()
  },
  
  methods: {
    // Validate IP address format
    isValidIP(ip) {
      const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
      return ipRegex.test(ip)
    },
    
    // Auto-update DHCP range based on router IP
    updateDHCPRange(routerIP) {
      if (!routerIP || !this.isValidIP(routerIP)) return
      
      try {
        // Split the IP into parts
        const ipParts = routerIP.split('.')
        const networkBase = `${ipParts[0]}.${ipParts[1]}.${ipParts[2]}`
        
        // Set DHCP range based on common patterns
        // Start from .100 and end at .200 (or adjust based on router IP)
        const routerLastOctet = parseInt(ipParts[3])
        
        let dhcpStart, dhcpEnd
        
        if (routerLastOctet === 1) {
          // Router is .1, use .100-.200 range
          dhcpStart = `${networkBase}.100`
          dhcpEnd = `${networkBase}.200`
        } else if (routerLastOctet <= 50) {
          // Router is low number, use .100-.200 range
          dhcpStart = `${networkBase}.100`
          dhcpEnd = `${networkBase}.200`
        } else if (routerLastOctet >= 200) {
          // Router is high number, use .50-.150 range
          dhcpStart = `${networkBase}.50`
          dhcpEnd = `${networkBase}.150`
        } else {
          // Router is in middle, avoid conflict
          dhcpStart = `${networkBase}.${routerLastOctet + 50}`
          dhcpEnd = `${networkBase}.${routerLastOctet + 100}`
          
          // Ensure we don't exceed 254
          if (parseInt(dhcpEnd.split('.')[3]) > 254) {
            dhcpStart = `${networkBase}.${routerLastOctet - 100}`
            dhcpEnd = `${networkBase}.${routerLastOctet - 50}`
          }
          
          // Ensure we don't go below 2
          if (parseInt(dhcpStart.split('.')[3]) < 2) {
            dhcpStart = `${networkBase}.100`
            dhcpEnd = `${networkBase}.200`
          }
        }
        
        // Update the DHCP range
        this.routerConfig.dhcpStart = dhcpStart
        this.routerConfig.dhcpEnd = dhcpEnd
        
        console.log(`Auto-updated DHCP range: ${dhcpStart} - ${dhcpEnd} based on router IP: ${routerIP}`)
        
      } catch (error) {
        console.error('Error updating DHCP range:', error)
      }
    },
    
    // Generate change preview text
    getChangePreviewText() {
      if (!this.routerConfig.routerIP) return ''
      
      const currentIP = this.currentRouterIP || 'Unknown'
      const newIP = this.routerConfig.routerIP
      const networkInterface = this.routerConfig.interface
      
      if (currentIP === newIP) {
        return `Router IP: ${newIP} on interface ${networkInterface} (no change)`
      }
      
      return `Router IP will change: ${currentIP} → ${newIP} on interface ${networkInterface}`
    },
    
    // Load current router configuration
    async loadCurrentConfig() {
      this.loadingCurrent = true
      try {
        const response = await getRouterIP()
        console.log('Router IP API response:', response) // Debug log
        if (response && response.success) {
          const config = response.data  // The router data is in response.data
          this.currentRouterIP = config.routerIP
          this.currentInterface = config.interface
          this.currentNetmask = config.netmask
          this.currentDHCPStart = config.dhcpStart
          this.currentDHCPEnd = config.dhcpEnd
          
          // Auto-populate form with current values
          this.routerConfig.routerIP = config.routerIP || ''
          this.routerConfig.interface = config.interface || 'lan'
          this.routerConfig.netmask = config.netmask || '255.255.255.0'
          this.routerConfig.dhcpStart = config.dhcpStart || ''
          this.routerConfig.dhcpEnd = config.dhcpEnd || ''
        }
      } catch (error) {
        console.error('Failed to load current router config:', error)
        this.$message.error('Failed to load current router configuration')
      } finally {
        this.loadingCurrent = false
      }
    },
    
    // Change router IP address
    async changeRouterIP() {
      this.$refs.routerForm.validate(async (valid) => {
        if (!valid) {
          this.$message.error('Please fix the form errors before changing router IP')
          return
        }
        
        // Confirmation dialog
        const confirmResult = await this.$confirm(
          `Are you sure you want to change the router IP from ${this.currentRouterIP} to ${this.routerConfig.routerIP}?\n\nThis will require reconnection to the router using the new IP address.`,
          'Confirm Router IP Change',
          {
            confirmButtonText: 'Yes, Change Router IP',
            cancelButtonText: 'Cancel',
            type: 'warning',
            dangerouslyUseHTMLString: true
          }
        ).catch(() => false)
        
        if (!confirmResult) return
        
        this.saveLoading = true
        try {
          const response = await setRouterIP({
            currentIP: this.currentRouterIP,
            newIP: this.routerConfig.routerIP,
            interface: this.routerConfig.interface,
            netmask: this.routerConfig.netmask,
            dhcpStart: this.routerConfig.dhcpStart,
            dhcpEnd: this.routerConfig.dhcpEnd
          })
          
          if (response.data && response.data.success) {
            this.$message.success('Router IP changed successfully!')
            
            // Update current configuration
            this.currentRouterIP = this.routerConfig.routerIP
            this.currentInterface = this.routerConfig.interface
            this.currentNetmask = this.routerConfig.netmask
            this.currentDHCPStart = this.routerConfig.dhcpStart
            this.currentDHCPEnd = this.routerConfig.dhcpEnd
            
            // Show reconnection message
            this.$alert(
              `Router IP has been changed to ${this.currentRouterIP}.\n\nPlease reconnect to the router using the new IP address.`,
              'Router IP Changed',
              {
                confirmButtonText: 'OK',
                type: 'success'
              }
            )
            
          } else {
            this.$message.error(response.data.message || 'Failed to change router IP')
          }
        } catch (error) {
          console.error('Change router IP error:', error)
          this.$message.error('Failed to change router IP: ' + (error.response?.data?.message || error.message))
        } finally {
          this.saveLoading = false
        }
      })
    },

    // Confirm reboot
    async confirmReboot() {
      try {
        await this.$confirm('Are you sure you want to reboot the router now?', 'Confirm Reboot', {
          confirmButtonText: 'Reboot',
          cancelButtonText: 'Cancel',
          type: 'warning'
        })
      } catch (e) {
        return
      }
      this.rebootLoading = true
      try {
        const res = await rebootSystem()
        if (res && res.success) {
          this.$message.success('Reboot initiated')
        } else {
          this.$message.error(res && res.message ? res.message : 'Failed to initiate reboot')
        }
      } catch (err) {
        console.error('Reboot error', err)
        this.$message.error('Failed to initiate reboot: ' + (err.message || 'Unknown'))
      } finally {
        this.rebootLoading = false
      }
    },

    // Confirm restart of router_proxy service
    async confirmRestart() {
      try {
        await this.$confirm('Restart the router proxy service? This will briefly interrupt functionality.', 'Confirm Restart', {
          confirmButtonText: 'Restart',
          cancelButtonText: 'Cancel',
          type: 'warning'
        })
      } catch (e) {
        return
      }
      this.restartLoading = true
      try {
        const res = await restartService()
        if (res && res.success) {
          this.$message.success('Restart command executed')
        } else {
          this.$message.error(res && res.message ? res.message : 'Failed to restart service')
        }
      } catch (err) {
        console.error('Restart error', err)
        this.$message.error('Failed to restart service: ' + (err.message || 'Unknown'))
      } finally {
        this.restartLoading = false
      }
    },
    
    // Test new IP connectivity
    async testNewIP() {
      const targetIP = this.routerConfig.routerIP
      if (!targetIP || !this.isValidIP(targetIP)) {
        this.$message.warning('Please enter a valid IP address to test')
        return
      }
      
      this.testLoading = true
      this.connectionStatus = 'testing'
      this.connectionMessage = `Testing ${targetIP}...`
      
      try {
        const response = await testRouterIP({
          testIP: targetIP,
          interface: this.routerConfig.interface
        })
        
        if (response.data && response.data.success) {
          this.connectionStatus = 'connected'
          this.connectionMessage = `IP ${targetIP} is available`
          this.$message.success('IP address test successful - no conflicts detected')
        } else {
          this.connectionStatus = 'failed'
          this.connectionMessage = response.data.message || `IP ${targetIP} test failed`
          this.$message.error(this.connectionMessage)
        }
      } catch (error) {
        console.error('IP test error:', error)
        this.connectionStatus = 'failed'
        this.connectionMessage = `IP test failed: ${error.response?.data?.message || error.message}`
        this.$message.error(this.connectionMessage)
      } finally {
        this.testLoading = false
      }
    },
    
    // Reset form
    resetForm() {
      this.routerConfig = {
        routerIP: '',
        interface: 'lan',
        netmask: '255.255.255.0',
        dhcpStart: '',
        dhcpEnd: ''
      }
      this.$refs.routerForm.clearValidate()
      this.connectionStatus = null
      this.connectionMessage = 'Not tested'
    },
    
    // Test backend connection
    async testConnection() {
      try {
        this.$message.info('Testing backend connection...')
        
        // Test health endpoint
        const response = await this.$http.get('/health')
        
        if (response && response.ok) {
          this.$message.success('Backend connection successful!')
          console.log('Backend response:', response)
        } else {
          this.$message.warning('Backend responded but with unexpected data')
          console.log('Backend response:', response)
        }
        
      } catch (error) {
        console.error('Backend connection test failed:', error)
        this.$message.error('Backend connection failed: ' + (error.message || 'Unknown error'))
      }
    },
    
    // Format date for display
    formatDate(date) {
      if (!date) return ''
      return new Date(date).toLocaleString()
    }
  }
}
</script>

<style scoped>
/* Container and Layout */
.app-container {
  padding: 20px;
}

.box-card {
  margin-bottom: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.card-title {
  font-size: 16px;
  font-weight: bold;
  color: #303133;
}

.clearfix:before,
.clearfix:after {
  display: table;
  content: "";
}

.clearfix:after {
  clear: both;
}

/* Form Styling */
.el-form {
  background-color: #fafafa;
  padding: 20px;
  border-radius: 6px;
}

.el-form-item {
  margin-bottom: 22px;
}

.el-input-group__prepend {
  background-color: #f5f7fa;
  border-color: #dcdfe6;
  color: #909399;
  font-weight: 500;
  width: 100px;
  text-align: center;
  height: 40px;
  line-height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.el-input__inner {
  text-align: left;
  vertical-align: middle;
  line-height: 40px;
  height: 40px;
  padding: 0 15px;
  font-size: 14px;
  display: flex;
  align-items: center;
}

.el-input-group {
  display: flex;
  align-items: stretch;
}

.el-input-group .el-input__inner {
  border-radius: 0;
}

.el-input-group__prepend + .el-input .el-input__inner {
  border-left: 0;
  border-radius: 0 4px 4px 0;
}

.el-input-group__append .el-button {
  border: none;
  background: transparent;
}

/* Current IP hint */
.current-ip-hint {
  margin-top: 5px;
  color: #909399;
}

.current-ip-hint .el-tag--mini {
  margin-left: 5px;
}

/* Alert Styling */
.el-alert {
  margin-bottom: 15px;
  border-radius: 6px;
}

.el-alert--warning {
  background-color: #fdf6ec;
  border-color: #faecd8;
}

.el-alert--info {
  background-color: #f4f4f5;
  border-color: #e9e9eb;
}

/* Status Tags */
.el-tag {
  font-weight: 500;
}

.el-tag--success {
  background-color: #f0f9ff;
  border-color: #67c23a;
  color: #67c23a;
}

.el-tag--primary {
  background-color: #ecf5ff;
  border-color: #409eff;
  color: #409eff;
}

.el-tag--danger {
  background-color: #fef0f0;
  border-color: #f56c6c;
  color: #f56c6c;
}

.el-tag--warning {
  background-color: #fdf6ec;
  border-color: #e6a23c;
  color: #e6a23c;
}

.el-tag--info {
  background-color: #f4f4f5;
  border-color: #909399;
  color: #909399;
}

/* Button Styling */
.el-button {
  border-radius: 4px;
  font-weight: 500;
}

.el-button--primary {
  background: linear-gradient(135deg, #409eff, #3a8ee6);
  border: none;
}

.el-button--success {
  background: linear-gradient(135deg, #67c23a, #5daf34);
  border: none;
}

/* Preset Buttons */
.preset-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
}

.preset-btn {
  height: auto !important;
  padding: 15px 20px;
  border-radius: 8px;
  transition: all 0.3s ease;
  border: 2px solid #dcdfe6;
}

.preset-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.preset-btn.el-button--success {
  border-color: #67c23a;
  background: linear-gradient(135deg, #67c23a, #5daf34);
}

.preset-content {
  text-align: center;
}

.preset-ip {
  font-weight: bold;
  font-size: 14px;
  margin-bottom: 4px;
}

.preset-desc {
  font-size: 12px;
  opacity: 0.8;
}

/* Descriptions */
.el-descriptions {
  background-color: #f8f9fa;
  border-radius: 6px;
}

.el-descriptions-item__label {
  font-weight: bold;
  color: #606266;
  background-color: #f5f7fa;
}

/* Badge */
.el-badge {
  display: inline-block;
}

/* Responsive Design */
@media (max-width: 768px) {
  .app-container {
    padding: 10px;
  }
  
  .el-form {
    padding: 15px;
  }
  
  .el-form-item__label {
    width: 140px !important;
  }
  
  .el-input, .el-select {
    width: 00% !important;
  }
  
  .preset-buttons {
    flex-direction: column;
  }
  
  .preset-btn {
    width: 100%;
  }
  
  .el-col {
    margin-bottom: 20px;
  }
}

/* Loading States */
.el-button.is-loading {
  pointer-events: none;
}

/* Animations */
.el-tag, .el-button {
  transition: all 0.3s ease;
}
</style>
