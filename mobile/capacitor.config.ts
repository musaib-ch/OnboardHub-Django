import type { CapacitorConfig } from '@capacitor/cli';

const portalUrl = process.env.ONBOARDHUB_URL;
if (!portalUrl || !/^https:\/\/[^\s]+$/i.test(portalUrl)) {
  throw new Error('ONBOARDHUB_URL must be a valid https:// URL, configured as repository variable PORTAL_URL.');
}
const config: CapacitorConfig = {
  appId: 'com.onboardhub.portal',
  appName: 'OnboardHub',
  webDir: 'www',
  server: { url: portalUrl, cleartext: false, androidScheme: 'https' },
  ios: { contentInset: 'automatic' },
  android: { allowMixedContent: false }
};
export default config;
