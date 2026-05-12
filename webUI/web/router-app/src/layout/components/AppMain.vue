<template>
  <section class="app-main">
    <transition name="fade-transform" mode="out-in">
      <keep-alive :include="cachedViews">
        <router-view :key="key" />
      </keep-alive>
    </transition>
    <div id="footer" v-html="footer_ads" />
  </section>
</template>

<script>
import {
  getFooterAds
} from '@/api/router-proxy/api'

export default {
  name: 'AppMain',
  data() {
    return {
      footer_ads: null
    }
  },
  computed: {
    cachedViews() {
      return this.$store.state.tagsView.cachedViews
    },
    key() {
      return this.$route.path
    }
  },
  created() {
    this.getConfig()
  },
  methods: {
    getConfig() {
      getFooterAds().then(response => {
        if (response.status) {
          this.footer_ads = response.data.content
        }
      })
    }
  }
}
</script>

<style lang="scss" scoped>

#footer {
    height: 160px!important;
    padding: 10px;
}

.app-main {
  /* 50= navbar  50  */
  min-height: calc(100vh - 50px);
  width: 100%;
  position: relative;
  overflow: hidden;
}

.fixed-header+.app-main {
  padding-top: 50px;
}

.hasTagsView {
  .app-main {
    /* 84 = navbar + tags-view = 50 + 34 */
    min-height: calc(100vh - 84px);
  }

  .fixed-header+.app-main {
    padding-top: 84px;
  }
}
</style>

<style lang="scss">
// fix css style bug in open el-dialog
.el-popup-parent--hidden {
  .fixed-header {
    padding-right: 15px;
  }
}
</style>
