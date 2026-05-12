<template>
  <div>
    <div v-for="(group, index) in groups" :key="index">
      <div class="input-with-checkbox">
        <el-input
          ref="inputRef"
          v-model="group.value"
          :placeholder="placeholder"
          @blur="onInputBlur(index)"
        />
        <el-checkbox
          v-if="checkbox_visible"
          v-model="group.default"
          class="checkbox1"
          @change="onCheckboxChange(group, index)"
        >Default
        </el-checkbox>
        <el-button class="remove-button1" icon="el-icon-delete" circle @click="removeComponent(index)" />
      </div>
    </div>

    <el-button class="add-button" icon="el-icon-plus" circle @click="addGroup" />
  </div>
</template>

<script>
export default {
  model: {
    prop: 'value', // Use the 'value' prop for v-model
    event: 'input' // Emit the 'input' event to update the v-model
  },
  props: {
    value: {
      type: Array,
      required: true
    },
    placeholder: {
      type: String,
      default: 'Input Text'
    },
    checkbox_visible: {
      type: Boolean,
      default: true
    }
  },
  data() {
    return {
      groups: this.value
    }
  },
  watch: {
    value(newValue, preValue) {
      this.groups = newValue
    }
  },
  methods: {
    removeComponent(index) {
      this.groups.splice(index, 1)
      this.$emit('input', this.groups) // Emit the updated groups array
      this.$emit('item_removed', index)
    },
    addGroup() {
      this.groups.push({
        value: '',
        default: false
      })
      this.$emit('input', this.groups) // Emit the updated groups array
      this.$emit('item_added', this.groups.length - 1)
    },
    onCheckboxChange(checkedGroup, checkedIndex) {
      if (checkedGroup.default) {
        this.groups.forEach((otherGroup, otherIndex) => {
          if (otherIndex !== checkedIndex && otherGroup.default) {
            otherGroup.default = false
          }
        })
        this.$emit('default_changed', checkedIndex)
        this.$emit('input', this.groups) // Emit the updated groups array
      } else {
        checkedGroup.default = true
      }
    },
    onInputBlur(index) {
      this.$emit('item_text_blur', index, this.groups[index].value)
    }
  }
}
</script>

<style scoped>
.input-with-checkbox {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.checkbox1 {
  margin-left: 10px;
}

.remove-button1 {
  margin-left: 10px;
}

.add-button {
  margin-top: 10px;
}
</style>
