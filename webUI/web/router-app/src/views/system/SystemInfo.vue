<template>
  <div class="system-info">
    <h2>System Information</h2>
    <el-tabs v-model="activeTab" type="card">
      <el-tab-pane label="License" name="license">
        <el-card class="box-card">
          <div>
            <strong>License Information</strong>
            <div class="license-info">
              <div class="license-row">
                <div class="license-label">Status</div>
                <div class="license-value">
                  <el-tag :type="licenseInfo.valid ? 'success' : 'danger'">
                    {{ licenseInfo.valid ? 'Valid' : 'Invalid' }}
                  </el-tag>
                </div>
              </div>
              <div class="license-row">
                <div class="license-label">Product Name</div>
                <div class="license-value">{{ licenseInfo.product_name || '-' }}</div>
              </div>
              <div class="license-row">
                <div class="license-label">Customer Name</div>
                <div class="license-value">{{ licenseInfo.customer_name || '-' }}</div>
              </div>
              <div class="license-row">
                <div class="license-label">Expiry Date</div>
                <div class="license-value">{{ licenseInfo.expiry_date ? licenseInfo.expiry_date.split('T')[0] : '-' }}</div>
              </div>
              <div class="license-row">
                <div class="license-label">Days Remaining</div>
                <div class="license-value">{{ licenseInfo.days_remaining !== undefined ? licenseInfo.days_remaining : '-' }}</div>
              </div>
            </div>
          </div>
          <div style="margin-top: 24px;">
            <el-form :inline="true" @submit.native.prevent="submitKey">
              <el-form-item label="License Key">
                <el-input v-model="inputKey" placeholder="Enter new license key" style="width: 350px;" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="submitKey">Submit</el-button>
              </el-form-item>
            </el-form>
            <div v-if="keyMessage" :style="{color: keyMessageType === 'success' ? 'green' : 'red'}">{{ keyMessage }}</div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="Software Update" name="update">
        <el-card class="box-card">
          <div class="license-info">
            <div class="license-row">
              <div class="license-label">Current Version</div>
              <div class="license-value">{{ versionInfo.current || '-' }}</div>
            </div>
            <div class="license-row">
              <div class="license-label">Latest Version</div>
              <div class="license-value">
                <span>{{ latestVersion || '-' }}</span>
                <el-tag v-if="updateAvailable" type="warning" style="margin-left: 8px;">Update available</el-tag>
                <el-tag v-else-if="latestVersion && !updateAvailable" type="success" style="margin-left: 8px;">Up to date</el-tag>
              </div>
            </div>
            <div class="license-row">
              <div class="license-label">Channel</div>
              <div class="license-value">{{ versionInfo.channel || 'stable' }}</div>
            </div>
            <div class="license-row">
              <div class="license-label">Pick Version</div>
              <div class="license-value">
                <el-select v-model="selectedVersion" placeholder="Latest" size="small" style="width: 220px;" clearable>
                  <el-option
                    v-for="v in versionList"
                    :key="v.version"
                    :label="v.version + (v.published_at ? ' (' + v.published_at.split('T')[0] + ')' : '')"
                    :value="v.version"
                  />
                </el-select>
              </div>
            </div>
          </div>

          <div style="margin-top: 16px;">
            <el-button :loading="checking" size="small" @click="onCheck">Check for updates</el-button>
            <el-button type="primary" size="small" :loading="busy" :disabled="!canInstall" @click="onApply">
              {{ selectedVersion ? 'Install selected' : 'Update to latest' }}
            </el-button>
            <el-button size="small" :disabled="!versionInfo.has_backup || busy" @click="onRollback">Rollback to previous</el-button>
          </div>

          <div v-if="updateState.phase && updateState.phase !== 'idle'" style="margin-top: 16px;">
            <el-progress
              :percentage="updateState.percent || 0"
              :status="progressStatus"
            />
            <div style="margin-top: 6px; color: #606266; font-size: 13px;">
              <strong>{{ updateState.phase }}</strong>
              <span v-if="updateState.message"> — {{ updateState.message }}</span>
            </div>
          </div>

          <div v-if="updateMessage" :style="{marginTop:'10px', color: updateMessageType === 'success' ? 'green' : 'red'}">
            {{ updateMessage }}
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import {
  getLicenseInfo, verifyLicenseKey, saveLicenseKey,
  getSystemVersion, checkUpdate, listUpdateVersions,
  applyUpdate, getUpdateStatus, rollbackUpdate
} from '@/api/router-proxy/api'

export default {
  name: 'SystemInfo',
  data() {
    return {
      activeTab: 'license',
      licenseInfo: {},
      inputKey: '',
      keyMessage: '',
      keyMessageType: 'success',
      versionInfo: {},
      latestVersion: '',
      updateAvailable: false,
      versionList: [],
      selectedVersion: '',
      updateState: { phase: 'idle', percent: 0, message: '' },
      checking: false,
      busy: false,
      pollTimer: null,
      updateMessage: '',
      updateMessageType: 'success'
    }
  },
  computed: {
    progressStatus() {
      if (this.updateState.phase === 'done') return 'success'
      if (this.updateState.phase === 'error') return 'exception'
      return null
    },
    canInstall() {
      if (this.busy) return false
      if (this.selectedVersion) return true
      return this.updateAvailable
    }
  },
  created() {
    this.fetchLicenseInfo()
    this.fetchVersion()
    this.fetchVersionList()
    this.refreshStatus()
  },
  beforeDestroy() {
    if (this.pollTimer) clearInterval(this.pollTimer)
  },
  methods: {
    async fetchLicenseInfo() {
      try {
        const res = await getLicenseInfo()
        this.licenseInfo = res || {}
      } catch (e) {
        this.licenseInfo = { valid: false }
      }
    },
    async submitKey() {
      if (!this.inputKey) {
        this.keyMessage = 'Please enter a license key.'
        this.keyMessageType = 'error'
        return
      }
      try {
        const saveRes = await saveLicenseKey(this.inputKey)
        if (saveRes && saveRes.success) {
          const res = await verifyLicenseKey(this.inputKey)
          if (res && res.valid) {
            this.keyMessage = 'License key saved and verified!'
            this.keyMessageType = 'success'
            this.fetchLicenseInfo()
          } else {
            this.keyMessage = (res && res.message) || 'License verification failed.'
            this.keyMessageType = 'error'
          }
        } else {
          this.keyMessage = (saveRes && saveRes.message) || 'Failed to save license key.'
          this.keyMessageType = 'error'
        }
      } catch (e) {
        this.keyMessage = 'Failed to save or verify license key.'
        this.keyMessageType = 'error'
      }
    },

    async fetchVersion() {
      try {
        const res = await getSystemVersion()
        this.versionInfo = res || {}
      } catch (e) {
        this.versionInfo = {}
      }
    },
    async onCheck() {
      this.checking = true
      this.updateMessage = ''
      try {
        const res = await checkUpdate()
        if (res && res.success) {
          this.latestVersion = res.latest || ''
          this.updateAvailable = !!res.update_available
          this.versionInfo = Object.assign({}, this.versionInfo, { current: res.current })
          this.fetchVersionList()
        } else {
          this.updateMessage = (res && res.message) || 'Check failed'
          this.updateMessageType = 'error'
        }
      } catch (e) {
        this.updateMessage = 'Failed to check for updates: ' + (e.message || e)
        this.updateMessageType = 'error'
      } finally {
        this.checking = false
      }
    },
    async fetchVersionList() {
      try {
        const res = await listUpdateVersions()
        if (res && res.success && Array.isArray(res.versions)) {
          this.versionList = res.versions
        }
      } catch (e) { /* ignore */ }
    },
    async onApply() {
      const target = this.selectedVersion || this.latestVersion || '(latest)'
      try {
        await this.$confirm(
          'Install version ' + target + '? The service will restart and the web UI may briefly disconnect.',
          'Confirm Update',
          { confirmButtonText: 'Install', cancelButtonText: 'Cancel', type: 'warning' }
        )
      } catch (e) { return }
      this.busy = true
      this.updateMessage = ''
      try {
        const res = await applyUpdate(this.selectedVersion || undefined)
        if (res && (res.success || res.state)) {
          this.updateState = (res.state) || this.updateState
          this.startPolling()
        } else {
          this.updateMessage = (res && res.message) || 'Failed to start update'
          this.updateMessageType = 'error'
          this.busy = false
        }
      } catch (e) {
        this.updateMessage = 'Failed to start update: ' + (e.message || e)
        this.updateMessageType = 'error'
        this.busy = false
      }
    },
    async onRollback() {
      try {
        await this.$confirm(
          'Rollback to the previous version? The service will restart.',
          'Confirm Rollback',
          { confirmButtonText: 'Rollback', cancelButtonText: 'Cancel', type: 'warning' }
        )
      } catch (e) { return }
      this.busy = true
      this.updateMessage = ''
      try {
        const res = await rollbackUpdate()
        this.updateState = (res && res.state) || this.updateState
        if (res && res.success) {
          this.updateMessage = 'Rollback initiated'
          this.updateMessageType = 'success'
          this.startPolling()
        } else {
          this.updateMessage = (res && res.message) || 'Rollback failed'
          this.updateMessageType = 'error'
          this.busy = false
        }
      } catch (e) {
        this.updateMessage = 'Rollback failed: ' + (e.message || e)
        this.updateMessageType = 'error'
        this.busy = false
      }
    },
    async refreshStatus() {
      try {
        const res = await getUpdateStatus()
        if (res && res.state) {
          this.updateState = res.state
          if (['downloading', 'verifying', 'installing', 'restarting'].indexOf(res.state.phase) !== -1) {
            this.busy = true
            this.startPolling()
          }
        }
      } catch (e) { /* ignore */ }
    },
    startPolling() {
      if (this.pollTimer) return
      const self = this
      this.pollTimer = setInterval(async () => {
        try {
          const res = await getUpdateStatus()
          if (res && res.state) {
            self.updateState = res.state
            if (['done', 'error', 'idle'].indexOf(res.state.phase) !== -1) {
              clearInterval(self.pollTimer)
              self.pollTimer = null
              self.busy = false
              if (res.state.phase === 'done') {
                self.updateMessage = 'Update complete. Service is restarting.'
                self.updateMessageType = 'success'
                setTimeout(() => { self.fetchVersion(); self.onCheck() }, 5000)
              } else if (res.state.phase === 'error') {
                self.updateMessage = 'Update failed: ' + (res.state.message || '')
                self.updateMessageType = 'error'
              }
            }
          }
        } catch (e) { /* keep polling */ }
      }, 2000)
    }
  }
}
</script>

<style scoped>
.system-info {
  max-width: 700px;
  margin: 40px auto;
}
.box-card {
  padding: 24px;
}
.license-info {
  margin-top: 8px;
}
.license-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f5f7fa;
}
.license-label {
  color: #606266;
  font-weight: 600;
  width: 160px;
}
.license-value {
  color: #303133;
  text-align: right;
  flex: 1;
}
.license-value el-tag {
  vertical-align: middle;
}
</style>
