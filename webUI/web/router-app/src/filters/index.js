// import parseTime, formatTime and set to filter
export { parseTime, formatTime } from '@/utils'

/**
 * Show plural label if time is plural number
 * @param {number} time
 * @param {string} label
 * @return {string}
 */
function pluralize(time, label) {
  if (time === 1) {
    return time + label
  }
  return time + label + 's'
}

export function limitStr(str, limit) {
  if (str.length <= limit) {
    return str
  } else {
    return str.substring(0, limit) + '...'
  }
}

/**
 * @param {number} time
 */

export function timeInWords(between) {
  if (between < 60) {
    return pluralize(~~(between), ' sec')
  } else if (between < 3600) {
    const minutes = Math.floor(between / 60)
    const seconds = Math.floor(between % 60)
    if (seconds === 0) {
      return pluralize(minutes, ' min')
    } else {
      return `${pluralize(minutes, ' min')}, ${pluralize(seconds, ' sec')}`
    }
  } else if (between < 86400) {
    const hours = Math.floor(between / 3600)
    const minutes = Math.floor((between % 3600) / 60)
    if (minutes === 0) {
      return pluralize(hours, ' hour')
    } else {
      return `${pluralize(hours, ' hour')}, ${pluralize(minutes, ' min')}`
    }
  } else {
    const days = Math.floor(between / 86400)
    const hours = Math.floor((between % 86400) / 3600)
    if (hours === 0) {
      return pluralize(days, ' day')
    } else {
      return `${pluralize(days, ' day')}, ${pluralize(hours, ' hour')}`
    }
  }
}

export function timeAgo(time) {
  if (time == null) {
    return '-'
  }
  const between = Date.now() / 1000 - Number(time)
  return timeInWords(between)
}

export function timeFutute(time, neg_text) {
  if (time == null) {
    return '-'
  }
  const between = Number(time) - Date.now() / 1000
  if (between >= 0) {
    return timeInWords(between)
  }
  return neg_text
}

export function ordinalSuffix(number) {
  if (number === 1) {
    return 'st'
  } else if (number === 2) {
    return 'nd'
  } else if (number === 3) {
    return 'rd'
  } else {
    return 'th'
  }
}

export function formatEpochToDate(epochTime) {
  const date = new Date(epochTime * 1000)
  const monthAbbrev = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ]
  return `${monthAbbrev[date.getMonth()]} ${('0' + date.getDate()).slice(-2)}, ${date.getFullYear()}`
}

export function formatEpochToDateTime(epochTime) {
  const date = new Date(epochTime * 1000)
  const monthAbbrev = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ]
  return `${monthAbbrev[date.getMonth()]} ${('0' + date.getDate()).slice(-2)}, ${date.getFullYear()} ${('0' + date.getHours()).slice(-2)}:${('0' + date.getMinutes()).slice(-2)}:${('0' + date.getSeconds()).slice(-2)}`
}

export function speedInWords(speedBps) {
  // Convert speed from bytes per second to a human-readable format
  const speedBits = speedBps * 8 // Convert bytes to bits

  if (speedBits > 1e9) { // Greater than 1 Gbps
    return (speedBits / 1e9).toFixed(2) + ' Gbps'
  } else if (speedBits > 1e6) { // Greater than 1 Mbps
    return (speedBits / 1e6).toFixed(2) + ' Mbps'
  } else if (speedBits > 1e3) { // Greater than 1 Kbps
    return (speedBits / 1e3).toFixed(2) + ' Kbps'
  } else {
    return speedBits + ' bps'
  }
}

/**
 * Number formatting
 * like 10000 => 10k
 * @param {number} num
 * @param {number} digits
 */
export function numberFormatter(num, digits) {
  const si = [
    { value: 1E18, symbol: 'E' },
    { value: 1E15, symbol: 'P' },
    { value: 1E12, symbol: 'T' },
    { value: 1E9, symbol: 'G' },
    { value: 1E6, symbol: 'M' },
    { value: 1E3, symbol: 'k' }
  ]
  for (let i = 0; i < si.length; i++) {
    if (num >= si[i].value) {
      return (num / si[i].value).toFixed(digits).replace(/\.0+$|(\.[0-9]*[1-9])0+$/, '$1') + si[i].symbol
    }
  }
  return num.toString()
}

/**
 * 10000 => "10,000"
 * @param {number} num
 */
export function toThousandFilter(num) {
  return (+num || 0).toString().replace(/^-?\d+/g, m => m.replace(/(?=(?!\b)(\d{3})+$)/g, ','))
}

/**
 * Upper case first char
 * @param {String} string
 */
export function uppercaseFirst(string) {
  return string.charAt(0).toUpperCase() + string.slice(1)
}
