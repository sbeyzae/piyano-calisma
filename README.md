# Piyano Çalışma Asistanı

JWIN SDP-112 dijital piyano için terminalden çalışan bir Python uygulaması: döngüyle beste yapma, solfej pratiği ve ton, akor, gam çalışması.

> **Durum:** Geliştirme aşamasında. Sahte MIDI portlarıyla test edildi (Python 3.13), gerçek piyano üzerinde henüz doğrulanmadı.

## Özellikler

### 1. Beste modu
- Çalınan ya da yazılan nota ve akorlar besteye eklenir ve döngü halinde tekrar edilir.
- `bitti` komutuyla döngü durur, beste `.mid` dosyası olarak kaydedilir (`mido` gerekir).

### 2. Solfej pratiği
- **Tekrarlı solfej:** Program bir bölümü çalar, kullanıcı tekrarlar.
- **Bireysel çalışma:** Program sıradaki notayı bekler; nota, vuruş ve es kontrol edilir, 100 üzerinden puan verilir.

### 3. Ton, akor ve gam
- **Öğren:** Diyez, bemol, donanım, ton, majör ve minör kavramları.
- **Yardımlı alıştırma:** Adım adım ipuçlarıyla ton bulma.
- **Puanlı sınav:** Donanım ve son notadan tonu bulup gamı çalma.
- **Akoru bas:** İstenen akoru çalma.
- **Kulak eğitimi:** Majör ve minör akorları ayırt etme (MIDI çıkışı gerekir).

İlk seviyedeki tonlar: C majör, A minör, F majör, D minör.

## Gereksinimler
- Python 3
- USB-MIDI ile bağlı dijital piyano (isteğe bağlı; bağlantı yoksa notalar klavyeden yazılabilir, ses çıkmaz)

## Kurulum

Proje klasöründe:

```bash
python -m venv .venv
```

Sanal ortamı etkinleştirin:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Paketleri kurun:

```bash
pip install -r requirements.txt
```

macOS ve Linux'ta ilk komut için `python3` yazmanız gerekebilir.

## Kullanım

| Komut | Açıklama |
|---|---|
| `python piyano.py` | Ana menü |
| `python piyano.py 1` | Beste modu |
| `python piyano.py 2` | Solfej pratiği |
| `python piyano.py 3` | Ton, akor ve gam |
| `python piyano.py portlar` | MIDI portlarını listeler |
| `python piyano.py 1 --port "USB"` | Adında "USB" geçen portu kullanır |

### Nota yazım biçimi

| Örnek | Anlamı |
|---|---|
| `do re mi` | Arka arkaya üç nota (her biri 1 vuruş) |
| `do+mi+sol:2` | 2 vuruşluk akor |
| `fa#`, `sib` | Diyez, bemol |
| `do5` | Oktav belirtme (varsayılan 4) |
| `es:1` | 1 vuruşluk es |

### Sık kullanılan komutlar

Her bölüm açıldığında kendi komut listesini gösterir.

| Komut | Nerede | Açıklama |
|---|---|---|
| `basla` | Solfej | Çalışmayı başlatır |
| `tempo 100`, `tempo adagio` | Beste, solfej | Hızı değiştirir |
| `tempolar` | Beste, solfej | Tempo sözlüğünü gösterir |
| `sil`, `temizle`, `goster` | Beste | Besteyi düzenler ve gösterir |
| `duraklat`, `devam` | Beste | Döngüyü yönetir |
| `ipucu` | Yardımlı alıştırma, akoru bas | Yardım verir |
| `bitti` | Tümü | Bulunulan bölümden çıkar |

## Proje yapısı

```
.
├── piyano.py          # Uygulamanın tamamı
├── requirements.txt   # Python paketleri
├── .gitignore
└── README.md
```

## Yol haritası
- [ ] Gerçek JWIN SDP-112 üzerinde test
- [ ] Akor yürüyüşü çalışması
- [ ] Beste modunda akor adlarını gösterme
- [ ] Yeni tonlar (aynı notada biten majör ve minör tonlar)
- [ ] Yalnızca dinleyerek ton bulma seviyesi
- [ ] İlerleme kaydı

## Sorun giderme
- **Piyano görünmüyor:** `python piyano.py portlar` ile portları kontrol edin; kablonun ve piyanonun USB-MIDI desteğini doğrulayın.
- **`python-rtmidi` kurulamıyor:** Kullandığınız Python sürümü için hazır paket olmayabilir; daha eski bir Python 3 sürümü deneyin.

## Lisans
Bu proje [MIT Lisansı](LICENSE) ile yayımlanmıştır.