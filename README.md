# Etsy Ekosistem V2

Windows için kişisel Etsy üretim stüdyosu. Mevcut uygulamadan ayrı sürümdür.

## Başlatma

1. ZIP'i tamamen klasöre çıkartın. ZIP'in içinden çalıştırmayın.
2. **BASLAT.cmd** dosyasını çift tıklayın. Panel `http://localhost:8766` adresinde açılır.
3. **Kurulum & bağlantı** ekranından kendi Etsy Keystring / Shared Secret bilgilerinizi kaydedin.
4. Etsy uygulamanıza `http://localhost:8766/oauth/etsy/callback` callback adresini ekleyin; **Etsy hesabını bağla** ile mağazanıza izin verin.
5. Photoshop'u seçin. **Şablon kütüphanesi** ekranında koleksiyon oluşturup PSD mockuplarınızı, isterseniz video PSD/MP4/MOV dosyanızı ekleyin.
6. Gelişmiş ayarlarda kendi CSV fiyat dosyalarınızı, kâr oranlarınızı, kargo profilinizi ve üretim ortağınızı ayarlayın.
7. Önce **Deneme** modunda ürün üretin. Hazır olduğunuzda **Etsy taslak** modunu seçin.

Kolay okunabilir tam rehber: **KULLANIM.html**.

**GitHub'dan indirenler:** Depoyu ZIP olarak indirin veya klonlayın; `BASLAT.cmd` ilk açılışta `setup.ps1` üzerinden Python ve sabitlenmiş bağımlılıkları indirir. İlk açılış internet ve yaklaşık 300 MB disk alanı gerektirir. Masaüstüne hazırlanan taşınabilir dağıtım ZIP'inde bu dosyalar zaten bulunur.

## Gereksinimler

- Windows 10/11 x64 (Intel/AMD), varsayılan web tarayıcısı.
- Photoshop, geçerli lisansı ve Smart Object içeren uyumlu PSD şablonları kullanıcı tarafından sağlanır.
- Kullanıcıya ait Etsy tarafından onaylanmış uygulama ve mağaza yetkisi gerekir.
- Python, Node.js veya Codex kurulumu gerekmez. Python ve bağımlılıkları `runtime/` içinde; panel önceden derlenmiştir.
- Etsy bağlantısı ve mağaza işlemleri internet gerektirir. Yerel panel ve dosya hazırlama internetsiz kullanılabilir.
- Video PSD için Photoshop sürümünün ve şablonun video dışa aktarım desteği gerekir. Hazır MP4/MOV koleksiyondaki tüm ürünlerde aynen kullanılır.
- Bu paket macOS/ARM64 için hazırlanmadı.

## Kişisel veriler ve dağıtım

Veritabanı, ürünler, şablon kopyaları, API anahtarları ve loglar `%LOCALAPPDATA%\EtsyEkosistemV2` altında saklanır. Her Windows kullanıcısının bağımsız verileri olur. Anahtarlar tarayıcıya geri döndürülmez. Yerel `secrets.json` dosyası işletim sistemi kullanıcı hesabı korumasına dayanır; bilgisayar hesabınıza erişen kişiler bu dosyaya erişebilir.

Arkadaşlarınıza yalnızca **etsy ekosistem v2 - dagitim.zip** dosyasını verin. Kişisel veri klasörünüzü paylaşmayın. Paketleme betiği sadece izin verilen uygulama dosyalarını ekler; logları, API bilgilerini, test verilerini ve ürünleri dışarıda bırakır. Aynı Windows kullanıcısındaki V2 kopyaları varsayılan olarak aynı V2 veri klasörünü kullanır. V1 verileriyle otomatik aktarım yapılmaz.

## Şablonlar ve üretim

- Her koleksiyonda 1–19 PSD olabilir. Listedeki ilk PSD kapaktır. Dosyalar numaralı adlarla kopyalanır; orijinalleri değişmez.
- Smart Object katman adı varsayılan `Kare 1`; gelişmiş ayarlardan değiştirilebilir. Tek Smart Object bulunan PSD'ler otomatik bulunur. Her üçüncü taraf PSD'nin karmaşık yapısıyla uyumluluk garanti edilmez; önce örnek üretin.
- Kullanıcıya özgü dört sabit bilgi görseli ve özel PSD dosya adı zorunluluğu V2'de kaldırıldı.
- Ürünler yerel kuyrukta oluşturulur; üretim ekranında ayrıca başlatılır. Deneme modu yeni ürünleri Etsy'ye göndermez.
- Etsy taslak modu ürünleri taslak oluşturur; yayınlama Etsy üzerinden yapılır. Mevcut ürün ekranındaki ayrıca onaylanan güncellemeler canlı Etsy ürünlerini değiştirir.
- Metinler mevcut motor gibi temel “Poster” metniyle başlar; yayından önce Etsy'de başlık/açıklama/etiketleri düzenleyin.
- Varyasyon motoru USD kullanır; otomatik kur dönüşümü yapmaz. Dijital varyasyon varsayılanı 14 USD / 999 stoktur. Fiziksel varyasyonlar için kendi CSV dosyalarınızı ekleyin.
- Varsayılan kâr marjı %40, çarpan 1.0. Marj: `maliyet / (1 - oran)`; maliyete yüzde ekleme: `maliyet * (1 + oran)`. Eski sabit fiyat tablosu ayrıca seçilebilir.
- CSV şeması mevcut motorla aynıdır; sonucu üretim ekranından kontrol edin.
- Photoshop'taki kişisel açık belgeleri kaydedip kapattıktan sonra üretim başlatın. Durdurma işlemleri otomasyon sırasında Photoshop'u da kapatabilir.

## Durdurma ve sorun giderme

Önce üretimi panelde durdurun, ardından **DURDUR.cmd** çalıştırın. Tarayıcı sekmesini kapatmak sunucuyu kapatmaz. DURDUR yalnızca aynı paket tarafından başlatılan V2 sunucusunu hedefler.

Panel açılmazsa `%LOCALAPPDATA%\EtsyEkosistemV2\logs\server.err.log` kaydını kontrol edin. 8766 portu doluysa diğer uygulamayı kapatın. V1 normalde 8765 portundadır. Etsy bağlantısında callback'in birebir eşleştiğini, uygulamanın onaylı olduğunu ve doğru mağazaya izin verdiğinizi kontrol edin. API anahtarlarını değiştirmek eski token ve mağaza kimliklerini temizler, deneme moduna döner. Aynı API anahtarlarıyla başka mağazaya geçmeden önce bağlantıyı kaldırın.

## Geliştirme

`src/` React + TypeScript; `server.py` Python; `v2_local.py` kurulum/kütüphane; `tools/` Photoshop otomasyonu. Arayüz geliştirmek için Node.js ve `build.ps1` gerekir; normal kullanımda gerekmez.

Test: `runtime\python.exe -B -m unittest discover -s tests -v`

Dağıtım: `runtime\python.exe -B tools\package_release.py`

`ETSY_V2_DATA_DIR` ve `ETSY_V2_PORT` ortam değişkenleri özel kurulum/test içindir. Port değişirse Etsy callback adresi de değişir. V1'in ETSY_* ortam anahtarları V2'ye otomatik aktarılmaz.

## Doğrulama

34 Python testi, üç yeni React ekranının kod seviyesinde render kontrolü, TypeScript kontrolü ve üretim derlemesi doğrulandı. Taşınabilir ortam içinde PIL, PDF, NumPy, OpenCV ve FFmpeg modülleri yüklendi. GitHub kaynaklarından ilk kurulum temiz bir klasörde denendi. Mevcut kaynakların SHA-256 değerleri korunmuştur.

Canlı Etsy yetkilendirmesi, mağazaya yazma, gerçek Photoshop/PSD/video üretimi ve ikinci fiziksel bilgisayar kurulumu bu teslimde çalıştırılmadı. Tarayıcı inceleme izni reddedildiği için görsel tarayıcı testi yapılmadı.

## Kaynaklar ve lisanslar

- [Etsy OAuth belgeleri](https://developers.etsy.com/documentation/essentials/authentication/)
- [Etsy yerel uygulama örneği](https://developers.etsy.com/documentation/tutorials/quickstart/)
- [Etsy uygulamalarım](https://www.etsy.com/developers/your-apps)
- [Python Windows embedded dağıtımı](https://www.python.org/downloads/release/python-31210/)

Python lisansı `runtime/LICENSE.txt`; paket lisansları `runtime/Lib/site-packages/*.dist-info` klasörlerindedir. FFmpeg lisans bilgileri `imageio_ffmpeg` paketindedir. Photoshop ve Etsy pakete dahil değildir; Etsy ile resmî ortaklık iddiası yoktur.

## CSV kaydetme ve mevcut ürünler

Ayarlar bölümündeki çerçevesiz ve çerçeveli CSV dosyalarını seçip Kaydet düğmesine basın. Kaydedilen dosya adları sayfa yenilendiğinde korunur. Boş veya uyumsuz CSV hata verir ve önceki kayıt korunur. Yeni ürünler bu dosyalardan otomatik varyasyon oluşturur. Daha önce açılan ürünlerde Varyasyon özeti altındaki Eksik CSV varyasyonlarını ekle düğmesini kullanın; mevcut varyasyonlar korunur.

Framed CSV içinde Assembly sütunu varsa yalnızca Ready-to-hang satırları alınır. USD tutarlarına kur dönüşümü uygulanmaz. Fiyatlandırma, paneldeki maliyet/kargo ve kâr oranı ayarlarına göre devam eder.

## Mockup ve video seçimi

Kütüphanede Mockup PSD dosyalarını seç veya Video veya video şablonu seç düğmesine basın. Standart dosya penceresinde klasörlerde gezip dosyaları seçin. Mockup için Ctrl ile 1–19 PSD, video için bir PSD/MP4/MOV seçilebilir. İptal mevcut seçimi korur; aynı dosya yeniden seçilebilir. Yol yazılmaz. Koleksiyonu kaydet ile seçilen dosyalar yalnızca bu bilgisayardaki panel sunucusuna parça parça aktarılır; dosya başına sınır 4 GB.

## Başlatma ve durdurma

BASLAT.cmd çalışma klasörü farklı olsa da paket içindeki run.ps1 dosyasını kullanır. Art arda başlatma tek sunucuyu paylaşır. Sunucuya proxy kullanmadan erişilir; açılış için 90 saniye beklenir. Sağlam Python kurulumu tekrar indirilmez; eksik bileşen varsa kurulum denenir. Port başka uygulamaya aitse o uygulama kapatılmaz, açıklayıcı hata gösterilir. Hatalar yerel veri klasöründeki logs klasörüne yazılır. DURDUR.cmd sunucunun kapanmasını bekler.

Windows üzerinde gerçek sunucuyla soğuk açılış, tekrar açılış, eşzamanlı iki başlatma, eksik/bozuk süreç kaydı, farklı çalışma klasöründen BASLAT.cmd ve dolu port testleri yapılır. Testler ayrı veri klasörü ve port kullanır; tarayıcı açmaz veya Etsy’ye bağlanmaz. Dosya seçiminin Windows penceresi ve gerçek Photoshop üretimi ikinci bilgisayarda ayrıca denenmelidir.
