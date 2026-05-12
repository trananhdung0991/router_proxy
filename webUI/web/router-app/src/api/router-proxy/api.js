import xrequest from '@/utils/xrequest'

export function statusList() {
  return xrequest({
    url: '/v2/status_list',
    method: 'get',
    timeout: 15000
  })
}

export function getManufactureInfo() {
  return xrequest({
    url: '/manufacture_information',
    method: 'get',
    timeout: 15000
  })
}

/* condition use */
export function getFooterAds() {
  return xrequest({
    url: '/v2/footer_ads',
    method: 'get',
    timeout: 15000
  })
}

export function getLinuxResource(data) {
  return xrequest({
    url: '/linux_resource',
    method: 'get',
    timeout: 15000
  })
}

export function getLicenseInfo() {
  return xrequest({
    url: '/license/info',
    method: 'get',
    timeout: 10000
  })
}

export function verifyLicenseKey(license_key) {
  return xrequest({
    url: '/license/verify',
    method: 'post',
    data: { license_key },
    timeout: 10000
  })
}

export function saveLicenseKey(license_key) {
  return xrequest({
    url: '/license/save',
    method: 'post',
    data: { license_key },
    timeout: 10000
  })
}

export function rebootSystem() {
  return xrequest({
    url: '/system/reboot',
    method: 'post',
    timeout: 10000
  })
}

export function restartService() {
  return xrequest({
    url: '/system/restart',
    method: 'post',
    timeout: 20000
  })
}
