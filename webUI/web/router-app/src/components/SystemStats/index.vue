<template>
  <div>
    <el-tooltip
      v-if="server_name != null && server_name !== ''"
      class="item"
      effect="dark"
      :content="'Server name: ' + server_name"
      placement="top-start"
    >
      <a
        href="#/system-info/index"
      > <span class="stats-info server-name">{{ server_name | limitStr(25) }}</span></a>
    </el-tooltip>
    <el-tooltip class="item" effect="dark" content="%CPU Usage" placement="top-start">
      <span class="stats-info">
        <svg-icon icon-class="cpu" class="cpu-svg" />{{ linuxCpu }}</span>
    </el-tooltip>
    <el-tooltip class="item" effect="dark" content="%RAM Usage" placement="top-start">
      <span class="stats-info">
        <svg-icon icon-class="ram" class="ram-svg" /> {{ linuxMemory }}</span>
    </el-tooltip>
    <el-tooltip class="item" effect="dark" content="Device Uptime" placement="top-start">
      <span class="stats-info">
        <svg-icon icon-class="uptime" class="uptime-svg" /> {{ linuxTimeUp }}
      </span>
    </el-tooltip>
    <el-tooltip class="item" effect="dark" content="System version" placement="top-start">
      <span class="stats-info">
        V{{ version }}
      </span>
    </el-tooltip>
  </div>
</template>

<script>
import {
  getLinuxResource
} from '@/api/router-proxy/api'

export default {
  name: 'LinuxResource',
  data() {
    return {
      timer: null,
      server_name: null,
      buyer_email: null,
      linuxCpu: null,
      linuxMemory: null,
      linuxTimeUp: null,
      version: null,
      updateAvailable: false,
      activated: false,
      endedSupport: false,
      update_info: null,
      updateText: null,
      max_modem: 0,
      plan_show_txt: null,
      plan_name: null,
      plan_starting_date: null,
      plan_ending_date: null,
      plan_remaining_day: null,
      is_connected_service: false,
      blink: ''
    }
  },
  deactivated() {
    clearInterval(this.timer)
  },
  beforeDestroy() {
    clearInterval(this.timer)
  },
  created() {
    this.getConfig()
    this.timer = setInterval(this.getConfig, 5000)
  },
  methods: {
    getConfig() {
      getLinuxResource().then(response => {
        this.linuxCpu = response.data.cpu + '%'
        this.linuxMemory = response.data.memory + '%'
        this.linuxTimeUp = response.data.time + 'h'
        this.version = response.data.version
        this.endedSupport = response.data.ended_support
        this.update_info = response.data.update_info
        this.activated = response.data.activated
        this.plan_name = response.data.plan_name
        this.max_modem = response.data.max_modem
        this.plan_starting_date = response.data.plan_starting_date
        this.plan_ending_date = response.data.plan_ending_date
        this.plan_remaining_day = response.data.plan_remaining_day
        this.is_connected_service = response.data.is_connected_service
        this.server_name = response.data.server_name
        this.buyer_email = response.data.buyer_email
        this.renderPlan()
        if (this.update_info != null) {
          this.updateAvailable = true
          this.updateText = this.update_info.need_update ? 'NEED UPDATE!' : this.update_info.heading
          this.blink = 'blink-1'
        } else {
          this.updateAvailable = false
          this.updateText = ''
        }
        if (response.data.is_updating) {
          window.location.reload(true)
        }
      })
    },
    renderPlan() {
      if (this.max_modem === -1) {
        this.plan_show_txt = 'LICENSE FAILURE (F)'
        this.blink = ''
        return
      }
      if (this.is_connected_service) {
        if (this.activated) {
          if (this.plan_name === 'free') {
            this.plan_show_txt = 'FREE LICENSE'
            this.endedSupport = false
            this.blink = ''
          } else if (this.plan_name === 'lifetime') {
            this.plan_show_txt = 'LIFETIME LICENSE'
            this.blink = ''
          } else {
            if (this.plan_remaining_day <= 0) {
              this.plan_show_txt = 'LICENSE EXPIRED'
              this.blink = 'blink-1'
            } else if (this.plan_remaining_day <= 5) {
              this.plan_show_txt = 'LICENSE WILL EXPIRED'
              this.blink = 'blink-2'
            } else {
              if (this.plan_name !== undefined) {
                this.plan_show_txt = this.plan_name !== null ? this.plan_name.toUpperCase() + ' LICENSE' : ''
                this.blink = ''
              }
            }
          }
        } else {
          this.plan_show_txt = "LET'S ACTIVATE"
          this.blink = 'blink-1'
        }
      } else {
        this.plan_show_txt = 'INTERNET/LICENSE ISSUES'
        this.blink = ''
      }
    }
  }
}
</script>

<style>
.stats-info {
  font-size: 22px;
  margin-left: 20px;
}

.server-name {
  font-size: 22px;
  line-height: 15px;
  padding: 6px;
}

.bold {
  font-weight: bold;
}

.red {
  color: red;
}

.free {
  color: #37a3f7;
}

.basic {
  color: #0056b3;
}

.premium {
  color: #c99e2c;
}

.business {
  color: #d9a10a;
}

@keyframes stats_blink {
  from {
    color: #010a18;
  }
  to {
    color: #338bf3;
  }
}

@-webkit-keyframes stats_blink {
  from {
    color: green;
  }
  to {
    color: white;
  }
}

.cpu-svg {
  font-size: 38px;
  vertical-align: -0.3em !important;
}

.ram-svg {
  font-size: 24px;
  vertical-align: -0.2em !important;
}

.uptime-svg {
  font-size: 35px;
  vertical-align: -0.3em !important;
}

a.blink-1 {
  animation-duration: 3000ms;
  animation-name: blink;
  animation-iteration-count: infinite;
  animation-direction: alternate;
  -webkit-animation: blink 2s steps(5, start) infinite; /* Safari and Chrome */
}

a.blink-2 {
  animation-duration: 1200ms;
  animation-name: blink;
  animation-iteration-count: infinite;
  animation-direction: alternate;
  -webkit-animation: blink 1200ms infinite; /* Safari and Chrome */
}

@keyframes blink {
  from {
    color: red;
  }
  to {
    color: white;
  }
}

@-webkit-keyframes blink {
  from {
    color: red;
  }
  to {
    color: white;
  }
}

@keyframes sub_blink {
  from {
    color: green;
  }
  to {
    color: blue;
  }
}
</style>
