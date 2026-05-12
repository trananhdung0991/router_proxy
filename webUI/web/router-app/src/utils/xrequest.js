import axios from 'axios'
import { Message } from 'element-ui'

axios.defaults.headers.common['Access-Control-Allow-Origin'] = '*'

// Auto-detect backend API URL based on current hostname
let backendAPI = process.env.VUE_APP_BACKEND_API

if (backendAPI === 'auto' || !backendAPI) {
  // Automatically construct the API URL using current hostname and port 8080
  const protocol = window.location.protocol // 'http:' or 'https:'
  const hostname = window.location.hostname // e.g., '192.168.1.1' or 'openwrt.local'
  backendAPI = `${protocol}//${hostname}:8080/`
  console.log('Auto-detected backend API URL:', backendAPI)
}

const service = axios.create({
  baseURL: backendAPI,
  // withCredentials: true, // send cookies when cross-domain requests
  timeout: 15000 // request timeout
})

// response interceptor
service.interceptors.response.use(
  /**
   * If you want to get http information such as headers or status
   * Please return  response => response
  */

  /**
   * Determine the request status by custom code
   * Here is just an example
   * You can also judge the status by HTTP Status Code
   */
  response => {
    const res = response.data
    return res
  },
  error => {
    console.log('err' + error) // for debug
    Message({
      message: error.message,
      type: 'error',
      duration: 5 * 1000
    })
    return Promise.reject(error)
  }
)

export default service
