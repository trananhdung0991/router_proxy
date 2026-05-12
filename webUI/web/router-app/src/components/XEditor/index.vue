<template>
  <div class="tui-editor-wrapper">
    <div ref="editorElement" class="editor-container" />
  </div>
</template>

<script>
// deps for editor
import 'codemirror/lib/codemirror.css' // codemirror
import 'tui-editor/dist/tui-editor.css' // editor ui
import 'tui-editor/dist/tui-editor-contents.css' // editor content
import Editor from 'tui-editor'

export default {
  model: {
    prop: 'modelValue', // Use the 'value' prop for v-model
    event: 'change' // Emit the 'input' event to update the v-model
  },
  props: {
    modelValue: {
      type: String,
      required: true,
      default: ''
    },
    height: {
      type: [Number, String],
      default: 300
    }
  },
  data() {
    return {
      initialValue: this.modelValue
    }
  },
  watch: {
    modelValue(newValue) {
      this.editor.setValue(newValue)
    }
  },
  mounted() {
    // Initialize the editor for the editorElement (editable)
    this.editor = new Editor({
      el: this.$refs.editorElement,
      initialValue: this.initialValue,
      height: this.height + 'px',
      exts: ['scrollSync'],
      toolbarItems: [],
      viewer: true,
      usageStatistics: false,
      hideModeSwitch: true,
      placeholder: 'Fill your template here'
    })

    this.editor.on('change', () => {
      const value = this.editor.getValue()
      this.$emit('change', value)
      // this.preview.setMarkdown(value)
    })
  },
  beforeDestroy() {
    this.editor.remove()
    // this.preview.remove()
  }
}
</script>

<style>
.menu-bar {
  display: flex;
  justify-content: center;
  margin-bottom: 10px;
}

.menu-bar button {
  padding: 5px 10px;
  margin: 0 5px;
  border: 1px solid #ccc;
  border-radius: 4px;
  cursor: pointer;
}

.menu-bar button.active {
  background-color: #007bff;
  color: #fff;
  border-color: #007bff;
}

.tui-editor-wrapper {
  display: flex;
}

.editor-container {
  flex: 1;
}

.preview-container {
  flex: 1;
}

/* Additional styles to visually disable the editor toolbar */
.tui-editor-contents {
  pointer-events: none;
  user-select: none;
}

div.te-toolbar-section {
  display: none !important;
}

.tui-editor-defaultUI .CodeMirror-lines {
  padding: 10px !important;
}

.te-md-container .CodeMirror {
  font-size: 16px !important;
}
</style>
