#include <SPI.h>
#include <MFRC522.h>
#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClientSecure.h> // PENTING: Library untuk HTTPS

// --- 1. KONFIGURASI WIFI ---
const char* ssid = "Infinix NOTE 40";
const char* password = "ikhsan123";

// --- 2. KONFIGURASI SERVER (VERCEL) ---
// Wajib pakai HTTPS
String serverBase = "https://iot-lac-mu.vercel.app"; 

// --- 3. KONFIGURASI RFID (NodeMCU) ---
#define SS_PIN D8
#define RST_PIN D3
MFRC522 mfrc522(SS_PIN, RST_PIN);

// Variabel Global
bool deviceIsActive = true;
unsigned long lastCheckTime = 0;
const long checkInterval = 5000; // Cek status tiap 5 detik

void setup() {
  Serial.begin(9600);
  SPI.begin();
  mfrc522.PCD_Init();

  // Koneksi WiFi
  WiFi.begin(ssid, password);
  Serial.print("Menghubungkan ke WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi Terhubung!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // A. Cek Status ON/OFF dari Server secara berkala
  if (millis() - lastCheckTime >= checkInterval) {
    cekStatusServer();
    lastCheckTime = millis();
  }

  // Jika status OFF, jangan lakukan scanning
  if (!deviceIsActive) {
    return; 
  }

  // B. Kode Baca RFID (Standar)
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  String uidString = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    uidString += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
    uidString += String(mfrc522.uid.uidByte[i], HEX);
  }
  uidString.toUpperCase();

  Serial.println("💳 Kartu Terdeteksi: " + uidString);

  // C. Kirim ke Server
  kirimDataKeServer(uidString);

  // Halt kartu agar tidak baca berulang cepat
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(1000);
}

// --- FUNGSI CEK STATUS (HTTPS) ---
void cekStatusServer() {
  if (WiFi.status() == WL_CONNECTED) {
    
    // GANTI JADI WiFiClientSecure UNTUK HTTPS
    WiFiClientSecure client;
    client.setInsecure(); // PENTING: Abaikan sertifikat SSL biar langsung konek
    
    HTTPClient http;
    
    // Pastikan path sesuai dengan route di Python kamu
    // Jika masih 404, coba tambah '/api' didepannya: serverBase + "/api/iot/check_active"
    http.begin(client, serverBase + "/iot/check_active"); 
    
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      
      // Debugging: Lihat apa balasan server
      // Serial.println("Respon Server: " + payload);

      // Cek apakah ada kata "true" di dalam JSON
      if (payload.indexOf("true") > 0) {
        if (!deviceIsActive) Serial.println("Status Berubah: ON (Aktif) ✅");
        deviceIsActive = true;
      } else {
        if (deviceIsActive) Serial.println("Status Berubah: OFF (Non-aktif) ❌");
        deviceIsActive = false;
      }
    } else {
      Serial.print("⚠️ Error Cek Status: ");
      Serial.println(httpCode);
    }
    http.end();
  }
}

// --- FUNGSI KIRIM DATA (HTTPS) ---
void kirimDataKeServer(String uid) {
  if (WiFi.status() == WL_CONNECTED) {
    
    WiFiClientSecure client;
    client.setInsecure(); // PENTING
    
    HTTPClient http;

    // Pastikan path sesuai
    http.begin(client, serverBase + "/iot/upload_uid");
    http.addHeader("Content-Type", "application/json");

    String jsonData = "{\"uid\":\"" + uid + "\"}";
    
    int httpResponseCode = http.POST(jsonData);
    
    if (httpResponseCode > 0) {
      Serial.println("🚀 Data terkirim! Kode: " + String(httpResponseCode));
    } else {
      Serial.println("⚠️ Gagal kirim data: " + String(httpResponseCode));
    }
    http.end();
  }
}