# ⚡ GitHub Actions Gecikmelerini Sıfırlama ve 7/24 Canlı Denizcilik Bildirimi

Bu doküman, GitHub Actions'ın standart zamanlanmış görevlerindeki (`schedule.cron`) **1 ila 3 saatlik kuyruk gecikmesini** tamamen ortadan kaldırarak; Türkiye karasularındaki gemi batma, alabora, acil durum ve hava uyarılarının **dakikalar veya saniyeler içinde** kullanıcılara ve Telegram botuna iletilmesini sağlayan **sıfır maliyetli (Zero-Ops / 100% Free)** çözümleri açıklar.

---

## 🔍 Problem: GitHub Actions Neden 2-3 Saat Gecikiyor?

GitHub Actions resmi dokümantasyonunda belirtildiği üzere:
> *"The schedule event can be delayed during periods of high loads of GitHub Actions runner queues."*

Dünya genelinde yüzbinlerce repo saat başlarında (`:00`) ve çeyrek geçelerde (`:15`, `:30`, `:45`) aynı anda tetiklendiği için GitHub Actions zamanlayıcısı kuyruğa girer ve 15 dakikalık bir cron **bazen 2-3 saat boyunca hiç çalışmayabilir**.

Acil bir deniz kazasında (batma, su alma veya alabora) 2 saatlik gecikme ölümcül olabilir.

---

## 🛠️ Çözüm Yolları (Sıfır Maliyet & Kesintisiz)

### 1. ÇÖZÜM: `repository_dispatch` ile Ücretsiz Dış Webhook Tetikleme (EN ÖNERİLEN)

GitHub Actions'da `schedule` gecikir; **ANCAK `repository_dispatch` bir kullanıcı eylemi (push gibi) sayıldığı için ASLA GECİKMEZ ve 15-30 saniye içinde çalışır!**

`.github/workflows/update.yml` dosyasına bu tetikleyici eklenmiştir:

```yaml
on:
  schedule:
    - cron: "7,22,37,52 * * * *"  # Kuyruk yoğunluğu olmayan tekli dakikalar
  repository_dispatch:
    types: [maritime_tick, ping, emergency]
  workflow_dispatch:
```

#### 2 Dakikalık Kurulum (Cron-Job.org — %100 Ücretsiz)

1. **[cron-job.org](https://cron-job.org)** adresinde ücretsiz hesap açın.
2. GitHub'dan bir **Personal Access Token (Classic)** oluşturun (`repo` ve `workflow` yetkisiyle).
3. Cron-Job.org üzerinde **"Create Cronjob"** butonuna tıklayın:
   - **Title:** `Maritime Watch 10m Ping`
   - **URL:** `https://api.github.com/repos/KeremKalyoncu/maritime-watch/dispatches`
   - **Request Method:** `POST`
   - **Request Headers:**
     - `Authorization: Bearer YOUR_GITHUB_PAT_TOKEN_HERE`
     - `Accept: application/vnd.github.v3+json`
     - `User-Agent: MaritimeWatch-Pinger`
   - **Request Body:** `{"event_type": "maritime_tick"}`
   - **Schedule:** Every 10 minutes (Her 10 dakikada bir).
4. **Kaydet** deyin.
✅ **Sonuç:** Artık GitHub Actions her 10 dakikada bir **0 saniye gecikmeyle** anında çalışır ve tüm Türk denizcilik uyarılarını günceller!

---

### 2. ÇÖZÜM: Cloudflare Workers Cron Trigger (Alternatif Serverless)

Cloudflare Workers günde 100.000 isteğe kadar %100 ücretsizdir (her 5 dakikada bir tetiklemek günde sadece 288 istek yapar).

Aşağıdaki kodu ücretsiz bir Cloudflare Worker'a yapıştırıp `Cron Trigger: */10 * * * *` ekleyebilirsiniz:

```javascript
export default {
  async scheduled(event, env, ctx) {
    const GITHUB_REPO = "KeremKalyoncu/maritime-watch";
    const GITHUB_TOKEN = env.GH_PAT; // Settings -> Variables altından ekleyin

    const res = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${GITHUB_TOKEN}`,
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MaritimeWatch-CF-Worker"
      },
      body: JSON.stringify({ event_type: "maritime_tick" })
    });

    console.log("GitHub trigger status:", res.status);
  }
};
```

---

### 3. ÇÖZÜM: Sürekli Çalışan Yerel / Mini-PC Daemon (Anlık Saniyeler İçinde Bot Yanıtı)

Eğer evinizde veya ofisinizde sürekli açık bir bilgisayar, Raspberry Pi veya eski bir laptop varsa:

```bash
# Windows:
scripts\run_daemon.bat

# Linux / Mac:
chmod +x scripts/run_daemon.sh
./scripts/run_daemon.sh
```

Bu script `python run.py --loop --send` çalıştırır; her 60 saniyede bir Türk karasularını tarar ve Telegram botuna atılan `/neredeyim`, `/mayday`, `/bogaz`, `/balikci` mesajlarını **2-3 saniye içinde anlık yanıtlar**.

---

## ⚓ Türk Denizcisine Özel Eklenen Yeni Bot Yetenekleri

| Komut | Açıklama |
| :--- | :--- |
| **`/neredeyim`** | GPS konumunuza göre en yakın Türk limanı, mesafesi (NM), kerteriz açısı (`092°`), Sahil Güvenlik 158 ve anlık Sefer Güvenlik Skoru. |
| **`/mayday`** | Acil durumda telsiz Kanal 16'dan okunacak imdat çağrısı metnini kullanıcının son konumuyla doldurulmuş hazır şablon olarak verir. |
| **`/bogaz`** | İstanbul ve Çanakkale Boğazları'nda transit gemi trafiği açık mı, sis nedeniyle askıya mı alındı? Anlık durum raporu. |
| **`/balikci [bölge]`** | Türk balıkçısına özel "Bugün denize çıkılır mı?" bülteni (dalga, hamle rüzgarı, Poyraz/Lodos analizi). |
| **`/kazalar`** | Türkiye karasularında (Şile, Boğazlar, Ege, Akdeniz) son bildirilen batan kosterler, alabora ve kurtarma operasyonları. |
| **`/abone [bölge]`** | Sadece kendi seçtiğiniz deniz bölgesinin (örn: Marmara veya Kuzey Ege) fırtına ve kaza alarmlarına abone olma. |
