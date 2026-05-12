import defaultSettings from '@/settings'

export default function getPageTitle(pageTitle) {
  if (pageTitle) {
    return `${defaultSettings.title} - ${pageTitle}`
  }
  return `${defaultSettings.title}`
}
