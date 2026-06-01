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
    });
    // Return Hex instead of base64 to avoid URL encoding issues with + and /
    return encrypted.ciphertext.toString(CryptoJS.enc.Hex);
  } catch (e) {
    return id;
  }
}

export function decryptId(token: string): string {
  try {
    // If it looks like old base64 URL encoded token, try decoding it first
    // but we expect hex now
    const isHex = /^[0-9a-fA-F]+$/.test(token);
    if (!isHex) {
      // Fallback for old tokens (base64)
      const decoded = decodeURIComponent(token);
      const bytes = CryptoJS.AES.decrypt(decoded, key, {
        iv: iv,
        mode: CryptoJS.mode.CBC,
        padding: CryptoJS.pad.Pkcs7
      });
      const original = bytes.toString(CryptoJS.enc.Utf8);
      return original || token;
    }

    const cipherParams = CryptoJS.lib.CipherParams.create({
      ciphertext: CryptoJS.enc.Hex.parse(token)
    });
    const bytes = CryptoJS.AES.decrypt(cipherParams, key, {
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
