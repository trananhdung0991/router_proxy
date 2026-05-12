<template>
  <div ref="rightPanel" :class="{show: show}" class="rightPanel-container">
    <div class="rightPanel-background" @click="togglePanelVisibility" />
    <div class="rightPanel">
      <div
        v-if="show"
        class="handle-button"
        :style="{'top': buttonTop+'px','background-color': '#ff4949'}"
        @click="togglePanelVisibility"
      >
        <i class="el-icon-close" />
      </div>
      <div class="rightPanel-items">
        <slot />
      </div>
    </div>
  </div>
</template>

<script>
import { addClass, removeClass } from '@/utils'

export default {
  name: 'RightPanel',
  props: {
    clickNotClose: {
      default: false,
      type: Boolean
    },
    buttonTop: {
      default: 250,
      type: Number
    },
    show: {
      default: false,
      type: Boolean
    },
    maxWidth: {
      default: '90%',
      type: String
    }
  },
  computed: {
    theme() {
      return this.$store.state.settings.theme
    }
  },
  watch: {
    show(value) {
      if (value) {
        addClass(document.body, 'showRightPanel')
        this.addEventClick()
      } else {
        removeClass(document.body, 'showRightPanel')
      }
    }
  },
  mounted() {
    if (this.show) {
      this.addEventClick()
    }
    this.insertToBody()
  },
  beforeDestroy() {
    const elx = this.$refs.rightPanel
    elx.remove()
  },
  methods: {
    addEventClick() {
      window.addEventListener('click', this.closeSidebar)
    },
    closeSidebar(evt) {
      const parent = evt.target.closest('.rightPanel')
      if (!parent) {
        window.removeEventListener('click', this.closeSidebar)
      }
    },
    togglePanelVisibility() {
      this.$emit('close-panel')
    },
    insertToBody() {
      const elx = this.$refs.rightPanel
      const body = document.querySelector('body')
      body.insertBefore(elx, body.firstChild)
    }
  }
}
</script>

<style>
.showRightPanel {
  overflow: hidden;
  position: relative;
  width: calc(100% - 15px);
}
</style>

<style lang="scss" scoped>
.rightPanel-background {
  position: fixed;
  top: 0;
  left: 0;
  opacity: 0;
  transition: opacity .3s cubic-bezier(.7, .3, .1, 1);
  background: rgba(0, 0, 0, .7);
  z-index: -1;
}

.rightPanel {
  width: 900px;
  height: 200vh;
  position: fixed;
  top: 0;
  right: 0;
  box-shadow: 0px 0px 15px 0px rgba(0, 0, 0, .05);
  transition: all .25s cubic-bezier(.7, .3, .1, 1);
  transform: translate(100%);
  background: #fff;
  z-index: 40000;
}

@media (min-width: 768px) and (max-width: 1023px) {
  /* Tablet styles */
  .rightPanel {
    width: 700px;
    max-width: 90%;
  }
}

@media (max-width: 767px) {
  /* Mobile styles */
  .rightPanel {
    width: 700px;
    max-width: 90%;
    min-width: unset;
  }
}

.show {
  transition: all .3s cubic-bezier(.7, .3, .1, 1);

  .rightPanel-background {
    z-index: 20000;
    opacity: 1;
    width: 100%;
    height: 100%;
  }

  .rightPanel {
    transform: translate(0);
  }
}

.rightPanel-items {

}

.handle-button {
  width: 48px;
  height: 48px;
  position: absolute;
  left: -48px;
  text-align: center;
  font-size: 24px;
  border-radius: 6px 0 0 6px !important;
  z-index: 0;
  pointer-events: auto;
  cursor: pointer;
  color: #fff;
  line-height: 48px;

  i {
    font-size: 24px;
    line-height: 48px;
  }
}

</style>
