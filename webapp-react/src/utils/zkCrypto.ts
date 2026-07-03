export const ZKCrypto = {
  async deriveMasterKey(password: string, email: string): Promise<CryptoKey> {
    const encoder = new TextEncoder();
    const baseKey = await window.crypto.subtle.importKey(
      "raw",
      encoder.encode(password),
      "PBKDF2",
      false,
      ["deriveKey"]
    );
    const salt = encoder.encode(email + "_sherpa_salt");
    return window.crypto.subtle.deriveKey(
      {
        name: "PBKDF2",
        salt: salt,
        iterations: 100000,
        hash: "SHA-256",
      },
      baseKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  },

  async encryptPrivateKey(privateKeyJwk: JsonWebKey, aesKey: CryptoKey): Promise<string> {
    const encoder = new TextEncoder();
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await window.crypto.subtle.encrypt(
      { name: "AES-GCM", iv: iv },
      aesKey,
      encoder.encode(JSON.stringify(privateKeyJwk))
    );
    const ivBase64 = btoa(String.fromCharCode(...iv));
    const ciphertextBase64 = btoa(String.fromCharCode(...new Uint8Array(encrypted)));
    return ivBase64 + ":" + ciphertextBase64;
  },

  async decryptPrivateKey(encryptedStr: string, aesKey: CryptoKey): Promise<JsonWebKey> {
    const parts = encryptedStr.split(":");
    if (parts.length !== 2) throw new Error("Invalid encrypted key format");
    const iv = new Uint8Array(atob(parts[0]).split("").map((c) => c.charCodeAt(0)));
    const ciphertext = new Uint8Array(atob(parts[1]).split("").map((c) => c.charCodeAt(0)));

    const decrypted = await window.crypto.subtle.decrypt(
      { name: "AES-GCM", iv: iv },
      aesKey,
      ciphertext
    );
    const decoder = new TextDecoder();
    return JSON.parse(decoder.decode(decrypted));
  },

  async generateRSAKeyPair(): Promise<CryptoKeyPair> {
    // Generates ECDH P-256 key pair instead of RSA for high performance
    return window.crypto.subtle.generateKey(
      {
        name: "ECDH",
        namedCurve: "P-256",
      },
      true,
      ["deriveKey", "deriveBits"]
    );
  },

  async exportPublicKeyPEM(publicKey: CryptoKey): Promise<string> {
    const exported = await window.crypto.subtle.exportKey("spki", publicKey);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(exported)));
    let pem = "-----BEGIN PUBLIC KEY-----\n";
    for (let i = 0; i < b64.length; i += 64) {
      pem += b64.substring(i, i + 64) + "\n";
    }
    pem += "-----END PUBLIC KEY-----";
    return pem;
  },

  async importPrivateKey(privateKeyJwk: JsonWebKey): Promise<CryptoKey> {
    if (privateKeyJwk.kty === "RSA") {
      return window.crypto.subtle.importKey(
        "jwk",
        privateKeyJwk,
        { name: "RSA-OAEP", hash: "SHA-256" },
        false,
        ["decrypt"]
      );
    } else {
      return window.crypto.subtle.importKey(
        "jwk",
        privateKeyJwk,
        { name: "ECDH", namedCurve: "P-256" },
        false,
        ["deriveKey", "deriveBits"]
      );
    }
  },

  async decryptRSA(encryptedBase64: string, privateKey: CryptoKey): Promise<string> {
    if (!encryptedBase64) return "";

    if (privateKey.algorithm.name === "RSA-OAEP") {
      const binary = atob(encryptedBase64);
      const array = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        array[i] = binary.charCodeAt(i);
      }
      const decrypted = await window.crypto.subtle.decrypt(
        { name: "RSA-OAEP" },
        privateKey,
        array
      );
      const decoder = new TextDecoder();
      return decoder.decode(decrypted);
    } else {
      // ECIES decryption: ECDH + HKDF + AES-GCM
      const binary = atob(encryptedBase64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }

      // Extract: Ephemeral Public Key (65 bytes), IV (12 bytes), Ciphertext (rest)
      const ephemeralPubBytes = bytes.slice(0, 65);
      const iv = bytes.slice(65, 77);
      const ciphertext = bytes.slice(77);

      // Import ephemeral public key
      const ephemeralPubKey = await window.crypto.subtle.importKey(
        "raw",
        ephemeralPubBytes,
        { name: "ECDH", namedCurve: "P-256" },
        true,
        []
      );

      // Key agreement to get shared secret bits
      const rawSharedSecret = await window.crypto.subtle.deriveBits(
        {
          name: "ECDH",
          public: ephemeralPubKey,
        },
        privateKey,
        256
      );

      // Import secret bits for HKDF
      const hkdfInputKey = await window.crypto.subtle.importKey(
        "raw",
        rawSharedSecret,
        { name: "HKDF" },
        false,
        ["deriveKey"]
      );

      // Derive AES-GCM symmetric key
      const aesKey = await window.crypto.subtle.deriveKey(
        {
          name: "HKDF",
          hash: "SHA-256",
          salt: new Uint8Array(0),
          info: new TextEncoder().encode("ecies-tradingbot-aes-gcm"),
        },
        hkdfInputKey,
        { name: "AES-GCM", length: 256 },
        false,
        ["decrypt"]
      );

      // Decrypt the ciphertext
      const decrypted = await window.crypto.subtle.decrypt(
        { name: "AES-GCM", iv: iv },
        aesKey,
        ciphertext
      );

      const decoder = new TextDecoder();
      return decoder.decode(decrypted);
    }
  },
};
