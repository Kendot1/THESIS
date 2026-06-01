import CryptoJS from 'crypto-js';

const SECRET = process.env.NEXT_PUBLIC_ID_SECRET || 'dev-secret-key';

// Use a deterministic key and IV for consistent URLs
const key = CryptoJS.SHA256(SECRET);
const iv = CryptoJS.enc.Utf8.parse("1234567890123456");

export function encryptId(id: string): string {
  try {
    const encrypted = CryptoJS.AES.encrypt(id, key, {
      iv: iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7
    }).toString();
    // Return URL-safe base64
    return encodeURIComponent(encrypted);
  } catch (e) {
    return encodeURIComponent(id);
  }
}

export function decryptId(token: string): string {
  try {
    const decoded = decodeURIComponent(token);
    const bytes = CryptoJS.AES.decrypt(decoded, key, {
      iv: iv,
      mode: CryptoJS.mode.CBC,
      padding: CryptoJS.pad.Pkcs7
    });
    const original = bytes.toString(CryptoJS.enc.Utf8);
    return original || token;
  } catch (e) {
    return token;
  }
}

export default { encryptId, decryptId };
