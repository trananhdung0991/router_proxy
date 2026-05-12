<template>
  <div class="system-info">
    <h2>System Information</h2>
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
  </div>
</template>

<script>
import { getLicenseInfo, verifyLicenseKey, saveLicenseKey } from '@/api/router-proxy/api'
export default {
  name: 'SystemInfo',
  data() {
    return {
      licenseInfo: {},
      inputKey: '',
      keyMessage: '',
      keyMessageType: 'success',
    };
  },
  created() {
    this.fetchLicenseInfo();
  },
  methods: {
    async fetchLicenseInfo() {
      try {
        const res = await getLicenseInfo();
        this.licenseInfo = res || {};
      } catch (e) {
        this.licenseInfo = { valid: false };
      }
    },
    async submitKey() {
      if (!this.inputKey) {
        this.keyMessage = 'Please enter a license key.';
        this.keyMessageType = 'error';
        return;
      }
      try {
        // Save license key to backend file using API function
        const saveRes = await saveLicenseKey(this.inputKey);
        // xrequest returns response.data directly, so saveRes is the data object
        if (saveRes && saveRes.success) {
          // Now verify the license key
          const res = await verifyLicenseKey(this.inputKey);
          if (res && res.valid) {
            this.keyMessage = 'License key saved and verified!';
            this.keyMessageType = 'success';
            this.fetchLicenseInfo();
          } else {
            this.keyMessage = (res && res.message) || 'License verification failed.';
            this.keyMessageType = 'error';
          }
        } else {
          this.keyMessage = (saveRes && saveRes.message) || 'Failed to save license key.';
          this.keyMessageType = 'error';
        }
      } catch (e) {
        this.keyMessage = 'Failed to save or verify license key.';
        this.keyMessageType = 'error';
      }
    },
  },
};
</script>

<style scoped>
.system-info {
  max-width: 600px;
  margin: 40px auto;
}
.box-card {
  padding: 24px;
}
/* License info rows */
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
