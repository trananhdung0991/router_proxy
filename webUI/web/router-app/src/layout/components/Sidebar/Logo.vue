<template>
  <div class="sidebar-logo-container" :class="{ collapse: collapse }">
    <transition name="sidebarLogoFade">
      <router-link v-if="collapse" key="collapse" class="sidebar-logo-link" to="/">
        <img v-if="logo" :src="logo" class="sidebar-logo">
      </router-link>
      <router-link v-else key="expand" class="sidebar-logo-link" to="/">
        <img v-if="logo1" :src="logo1" class="sidebar-logo">
      </router-link>
    </transition>
  </div>
</template>

<script>
import {
  getManufactureInfo
} from '@/api/router-proxy/api'
import defaultSettings from '../../../settings.js'

export default {
  name: 'SidebarLogo',
  props: {
    collapse: {
      type: Boolean,
      required: true
    }
  },
  data() {
    return {
      title: '',
      name: '',
      identity_name: '',
      logo: undefined,
      logo1: undefined
    }
  },
  created() {
    getManufactureInfo().then(response => {
      this.name = response.data.name
      this.identity_name = response.data.identity_name
      defaultSettings.title = response.data.name
      defaultSettings.api_document = response.data.api_ref
      this.logo = require('@/assets/img/logo/' + this.identity_name + '_small.png')
      this.logo1 = require('@/assets/img/logo/' + this.identity_name + '_large.png')
      document.title = defaultSettings.title + ' ' + document.title
    })
  }
}
</script>

<style lang="scss" scoped>
.sidebarLogoFade-enter-active {
    transition: opacity 1.5s;
}
.sidebarLogoFade-enter,
.sidebarLogoFade-leave-to {
    opacity: 0;
}
.sidebar-logo-container {
    position: relative;
    width: 100%;
    height: 50px;
    line-height: 50px;
    background: #e6ebf5;
    text-align: center;
    overflow: hidden;
    & .sidebar-logo-link {
        height: 100%;
        width: 100%;
        & .sidebar-logo {
            height: 100%;
            width: 100%;
            vertical-align: middle;
        }
        & .sidebar-title {
            display: inline-block;
            margin: 0;
            color: #dadadc;
            font-weight: 600;
            line-height: 50px;
            font-size: 14px;
            font-family: Avenir, Helvetica Neue, Arial, Helvetica, sans-serif;
            vertical-align: middle;
        }
    }
    &.collapse {
        .sidebar-logo {
            margin-right: 0px;
        }
    }
}
</style>
