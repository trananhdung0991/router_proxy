import Vue from 'vue'
import { getManufactureInfo } from '@/api/router-proxy/api'

// Reactive shared state so UI updates when identity is loaded
export const identityState = Vue.observable({
  name: '',
  identity_name: '',
  api_document: ''
})

let loaded = false
let loadPromise = null

export async function loadIdentity() {
  if (loaded && identityState.identity_name) return identityState
  if (!loadPromise) {
    loadPromise = getManufactureInfo()
      .then(res => {
        const data = (res && res.data) || {}
        identityState.name = data.name || ''
        identityState.identity_name = data.identity_name || ''
        identityState.api_document = data.api_ref || ''
        loaded = true
        return identityState
      })
      .catch(() => {
        loaded = true
        return identityState
      })
  }
  return loadPromise
}

export function getIdentityName() {
  return identityState.identity_name || ''
}

export function isIdentity(...names) {
  const id = identityState.identity_name
  if (!id) return false
  return names.includes(id)
}
