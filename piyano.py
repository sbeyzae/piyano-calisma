#!/usr/bin/env python3
"""
JWIN SDP-112 için beste döngüsü, solfej pratiği ve ton çalışması.

Kurulum:   pip install mido python-rtmidi
Çalıştır:  python piyano.py          (menü açılır)
           python piyano.py 1        (doğrudan beste modu)
           python piyano.py 2        (doğrudan solfej modu)
           python piyano.py 3        (doğrudan ton, akor ve gam çalışması)
           python piyano.py portlar  (MIDI portlarını listeler)
           python piyano.py 1 --port "USB"   (adında "USB" geçen portu seçer)

Notalar piyanodan (MIDI) çalınabilir ya da klavyeden yazılabilir:
    do re mi          arka arkaya üç nota (her biri 1 vuruş)
    do+mi+sol:2       aynı anda üç nota (akor), 2 vuruş
    fa#  sib  do5     diyez, bemol, oktav (varsayılan 4 = orta do)
    es:1              1 vuruşluk sus
"""
import argparse
import datetime
import queue
import random
import re
import threading
import time

try:
    import mido
except ImportError:
    mido = None

# ------------------------------------------------------------------ AYARLAR
VARSAYILAN_TEMPO = 80      # dakikadaki vuruş sayısı
AKOR_PENCERESI = 0.06      # sn; bu süre içinde basılan tuşlar akor sayılır
EN_UZUN_VURUS = 8

# Tempo sözlüğü: ad: (BPM aralığı, programın kullandığı BPM, anlamı)
# Aralıklar yaklaşıktır, kaynaktan kaynağa değişir.
TEMPOLAR = {
    "larghissimo": ("24 ve altı", 22, "son derece yavaş"),
    "grave":       ("25-45",      35, "ağır ve ciddi"),
    "largo":       ("40-60",      50, "çok yavaş, geniş"),
    "lento":       ("45-60",      54, "yavaş"),
    "larghetto":   ("60-66",      63, "largo'dan biraz hızlı"),
    "adagio":      ("66-76",      70, "yavaş ve sakin"),
    "adagietto":   ("70-80",      74, "adagio'dan biraz hızlı"),
    "andante":     ("76-108",     88, "yürüyüş hızında"),
    "andantino":   ("80-108",     96, "genellikle andante'den biraz hızlı"),
    "moderato":    ("108-120",   112, "orta hızda"),
    "allegretto":  ("112-120",   116, "oldukça canlı"),
    "allegro":     ("120-156",   132, "hızlı, neşeli"),
    "vivace":      ("156-176",   164, "canlı ve hızlı"),
    "vivo":        ("156-176",   168, "canlı, hareketli"),
    "vivacissimo": ("172-176",   174, "çok canlı ve hızlı"),
    "presto":      ("168-200",   184, "çok hızlı"),
    "prestissimo": ("200 ve üstü", 208, "olabildiğince hızlı"),
}

# Günün çalışması bu listeden tarihe göre sırayla seçilir. Yenisini ekleyebilirsin.
SOLFEJLER = [
    "do re mi fa sol:2 sol:2",
    "sol fa mi re do:2 do:2",
    "do mi re fa mi sol fa:0.5 mi:0.5 re do:2",
    "do do sol sol la la sol:2",
    "do mi sol do5:2 sol mi do:2",
    "mi mi fa sol sol fa mi re do do re mi mi:1.5 re:0.5 re:2",
    "do re:0.5 mi:0.5 fa sol:0.5 la:0.5 sol:2 es do:2",
]

NOTALAR = {"do": 0, "re": 2, "mi": 4, "fa": 5, "sol": 7, "la": 9, "si": 11}
ADLAR = ["do", "do#", "re", "re#", "mi", "fa", "fa#", "sol", "sol#", "la", "la#", "si"]
NOTA_DESENI = re.compile(r"^(do|re|mi|fa|sol|la|si)(#|b)?([1-7])?$")


# ------------------------------------------------------------------ NOTA İŞLEMLERİ
# Bir "adım" = (notalar, vurus). notalar boşsa sus demektir.

def sadelestir(metin):
    """Türkçe büyük/küçük harf sorunlarını giderir (BİTTİ -> bitti)."""
    metin = metin.replace("İ", "i").lower()
    return metin.translate(str.maketrans("ışçöüğ", "iscoug")).strip()


def adim_coz(parca):
    """'do+mi:2' gibi bir yazıyı adıma çevirir. Hatalıysa ValueError verir."""
    govde, ayrac, sure = parca.partition(":")
    vurus = float(sure.replace(",", ".")) if ayrac else 1.0
    if not 0 < vurus <= EN_UZUN_VURUS:
        raise ValueError(parca)
    if govde == "es":
        return ((), vurus)
    notalar = []
    for ad in govde.split("+"):
        eslesme = NOTA_DESENI.match(ad)
        if not eslesme:
            raise ValueError(parca)
        nota, isaret, oktav = eslesme.groups()
        kayma = {"#": 1, "b": -1, None: 0}[isaret]
        notalar.append(12 * (int(oktav or 4) + 1) + NOTALAR[nota] + kayma)
    return (tuple(sorted(set(notalar))), vurus)


def satir_coz(satir):
    return [adim_coz(p) for p in satir.split()]


def nota_adi(numara):
    return f"{ADLAR[numara % 12]}{numara // 12 - 1}"


def adim_yaz(adim):
    notalar, vurus = adim
    ad = "+".join(nota_adi(n) for n in notalar) or "es"
    return f"{ad}:{vurus:g}"


def tempo_coz(deger):
    """'adagio' ya da '100' -> BPM. Geçersizse None."""
    if deger in TEMPOLAR:
        return TEMPOLAR[deger][1]
    if deger.isdecimal() and 20 <= int(deger) <= 240:
        return int(deger)
    return None


def tempo_listele():
    print("\nTempo sözlüğü (yavaştan hızlıya)")
    for ad, (aralik, bpm, anlam) in TEMPOLAR.items():
        print(f"  {ad.capitalize():<12} {aralik:<12} (ayar: {bpm:>3})  {anlam}")


TEMPO_KULLANIM = "Kullanım: tempo 20-240 ya da tempo adagio (adlar için: tempolar)"


# ------------------------------------------------------------------ MIDI
class TusToplayici:
    """Piyanodan gelen tuş mesajlarını nota / akor adımlarına dönüştürür."""

    def __init__(self, gonder):
        self.pencere = AKOR_PENCERESI
        self.gonder = gonder          # gonder(notalar, saniye, baslangic)
        self.basili = set()
        self.grup = set()
        self.baslangic = None

    def mesaj(self, msg):
        if msg.type not in ("note_on", "note_off"):
            return
        simdi = time.monotonic()
        if msg.type == "note_on" and msg.velocity > 0:
            # Yeni basış akor penceresinin dışındaysa önceki grubu kapat (legato)
            if self.baslangic is not None and simdi - self.baslangic > self.pencere:
                self._kapat(simdi)
            if self.baslangic is None:
                self.baslangic = simdi
            self.grup.add(msg.note)
            self.basili.add(msg.note)
        else:
            self.basili.discard(msg.note)
            if self.baslangic is not None and not (self.grup & self.basili):
                self._kapat(simdi)

    def _kapat(self, simdi):
        self.gonder(tuple(sorted(self.grup)), simdi - self.baslangic, self.baslangic)
        self.grup = set()
        self.baslangic = None


class Piyano:
    """MIDI giriş/çıkışı. Bağlantı yoksa program yazılı modda çalışır."""

    def __init__(self, olaylar, port_filtresi=""):
        self.giris = self.cikis = self.toplayici = None
        self.durum = []
        if mido is None:
            self.durum.append("mido kurulu değil: yazılı mod (ses yok).")
            return
        try:
            toplayici = self.toplayici = TusToplayici(lambda *veri: olaylar.put(("midi", veri)))
            giris_adi = self._sec(mido.get_input_names(), port_filtresi)
            cikis_adi = self._sec(mido.get_output_names(), port_filtresi)
            if giris_adi:
                self.giris = mido.open_input(giris_adi, callback=toplayici.mesaj)
            if cikis_adi:
                self.cikis = mido.open_output(cikis_adi)
            self.durum.append(f"MIDI giriş: {giris_adi or 'yok (notaları yazabilirsin)'}")
            self.durum.append(f"MIDI çıkış: {cikis_adi or 'yok (ses çıkmaz)'}")
        except Exception as hata:
            self.durum.append(f"MIDI açılamadı ({hata}): yazılı mod.")

    @staticmethod
    def _sec(adlar, filtre):
        if filtre:
            adlar = [a for a in adlar if filtre.lower() in a.lower()]
        # Sanal portları sona at, gerçek cihazı tercih et
        sanal = ("through", "wavetable")
        adlar = sorted(adlar, key=lambda a: any(s in a.lower() for s in sanal))
        return adlar[0] if adlar else None

    def akor_penceresi(self, saniye):
        if self.toplayici:
            self.toplayici.pencere = saniye

    def cal(self, adim, tempo, dur=None):
        """Bir adımı piyanoda çalar. dur işaretlenirse hemen susar."""
        dur = dur or threading.Event()
        notalar, vurus = adim
        saniye = vurus * 60 / tempo
        try:
            if self.cikis:
                for n in notalar:
                    self.cikis.send(mido.Message("note_on", note=n, velocity=75))
            dur.wait(saniye * 0.92)
        finally:
            if self.cikis:
                for n in notalar:
                    self.cikis.send(mido.Message("note_off", note=n))
        dur.wait(saniye * 0.08)

    def kapat(self):
        if self.cikis:
            self.cikis.send(mido.Message("control_change", control=123, value=0))
            self.cikis.close()
        if self.giris:
            self.giris.close()


# ------------------------------------------------------------------ 1) BESTE MODU
class Dongu(threading.Thread):
    """Besteyi arka planda sürekli tekrar eder; eklenen notalar döngüye katılır."""

    def __init__(self, piyano):
        super().__init__(daemon=True)
        self.piyano = piyano
        self.beste = []
        self.tempo = VARSAYILAN_TEMPO
        self.kilit = threading.Lock()
        self.dur = threading.Event()
        self.duraklat = threading.Event()

    def run(self):
        sira = 0
        while not self.dur.is_set():
            adim, tur_sonu = None, False
            with self.kilit:
                if self.beste and not self.duraklat.is_set():
                    sira = sira if sira < len(self.beste) else 0
                    adim = self.beste[sira]
                    sira += 1
                    tur_sonu = sira >= len(self.beste)
            if adim is None:
                self.dur.wait(0.05)
                continue
            self.piyano.cal(adim, self.tempo, self.dur)
            if tur_sonu:
                # Turlar arasında 1 vuruş nefes. Bu sırada eklenen nota hemen sıradaki olur.
                with self.kilit:
                    yeni_var = sira < len(self.beste)
                if not yeni_var:
                    self.dur.wait(60 / self.tempo)


def midi_kaydet(beste, tempo):
    if mido is None or not beste:
        return None
    dosya = mido.MidiFile(ticks_per_beat=480)
    iz = mido.MidiTrack()
    dosya.tracks.append(iz)
    iz.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo)))
    bekleme = 0
    for notalar, vurus in beste:
        tik = int(vurus * 480)
        if not notalar:
            bekleme += tik
            continue
        for i, n in enumerate(notalar):
            iz.append(mido.Message("note_on", note=n, velocity=75, time=bekleme if i == 0 else 0))
        for i, n in enumerate(notalar):
            iz.append(mido.Message("note_off", note=n, time=tik if i == 0 else 0))
        bekleme = 0
    iz.append(mido.MetaMessage("end_of_track", time=bekleme))
    ad = f"beste_{datetime.datetime.now():%Y%m%d_%H%M%S}.mid"
    dosya.save(ad)
    return ad


BESTE_YARDIM = """Komutlar:
  bitti      döngüyü durdur, besteyi kaydet
  sil        son eklenen adımı sil
  temizle    tüm besteyi sil
  goster     besteyi yazdır
  duraklat   döngüyü beklet        devam   sürdür
  tempo 100  hızı değiştir         tempo adagio  isimle hız seç
  tempolar   tempo sözlüğü         yardim  bu listeyi göster"""


def beste_modu(piyano, olaylar):
    print("\n--- BESTE MODU ---")
    print(*piyano.durum, sep="\n")
    print("Piyanodan çal ya da nota yaz (ör: do re mi+sol:2).")
    print(BESTE_YARDIM)
    dongu = Dongu(piyano)
    dongu.start()
    try:
        while True:
            tur, veri = olaylar.get()
            if tur == "midi":
                notalar, saniye, _ = veri
                vurus = round(saniye * dongu.tempo / 60 * 4) / 4   # 1/4 vuruşa yuvarla
                adim = (notalar, min(max(vurus, 0.25), EN_UZUN_VURUS))
                with dongu.kilit:
                    dongu.beste.append(adim)
                print("Eklendi:", adim_yaz(adim))
                continue

            komut = sadelestir(veri)
            if komut in ("bitti", "cikis"):
                break
            elif komut == "sil":
                with dongu.kilit:
                    silinen = dongu.beste.pop() if dongu.beste else None
                print("Silindi:", adim_yaz(silinen)) if silinen else print("Beste boş.")
            elif komut == "temizle":
                with dongu.kilit:
                    dongu.beste.clear()
                print("Beste temizlendi.")
            elif komut == "goster":
                print("Beste:", " ".join(map(adim_yaz, dongu.beste)) or "(boş)")
            elif komut == "duraklat":
                dongu.duraklat.set()
                print("Döngü duraklatıldı.")
            elif komut == "devam":
                dongu.duraklat.clear()
                print("Döngü sürüyor.")
            elif komut == "yardim":
                print(BESTE_YARDIM)
            elif komut == "tempolar":
                tempo_listele()
            elif komut.startswith("tempo"):
                bpm = tempo_coz(komut[5:].strip())
                if bpm:
                    dongu.tempo = bpm
                    print("Tempo:", bpm)
                else:
                    print(TEMPO_KULLANIM)
            elif komut:
                try:
                    yeni = satir_coz(komut)
                except ValueError as hata:
                    print(f"Anlaşılamadı: {hata}  (yardim yazabilirsin)")
                    continue
                with dongu.kilit:
                    dongu.beste.extend(yeni)
                print("Eklendi:", " ".join(map(adim_yaz, yeni)))
    finally:
        dongu.dur.set()
        dongu.join()

    if dongu.beste:
        print("\nBesten:", " ".join(map(adim_yaz, dongu.beste)))
        dosya = midi_kaydet(dongu.beste, dongu.tempo)
        if dosya:
            print("Kaydedildi:", dosya)


# ------------------------------------------------------------------ 2) SOLFEJ MODU
SURE_ADLARI = {0.5: "sekizlik", 1: "dörtlük", 1.5: "noktalı dörtlük",
               2: "ikilik", 3: "noktalı ikilik", 4: "birlik"}
BOLUM_UZUNLUGU = 4      # tekrarlı pratikte bir bölümdeki nota sayısı

BIREYSEL_YARDIM = """Komutlar:
  basla      çalışmaya başla        bastan   en baştan başla
  dinle      tüm çalışmayı dinlet   tekrar   sıradaki notayı dinlet
  gec        bu notayı atla (0 puan)
  tempo 70 / tempo adagio           tempolar tempo sözlüğü
  yardim     bu liste               bitti    solfej menüsüne dön"""

TEKRARLI_YARDIM = """Komutlar:
  basla      çalışmaya başla        bastan   ilk bölümden başla
  tekrar     bölümü yeniden dinlet  gec      sonraki bölüme geç
  bolum 3    bölümdeki nota sayısı (1-16)
  tempo 70 / tempo adagio           tempolar tempo sözlüğü
  yardim     bu liste               bitti    solfej menüsüne dön"""


def notalara_ayir(adimlar):
    """Adımları (önceki_es, notalar, vurus) listesine çevirir."""
    sonuc, es = [], 0
    for notalar, vurus in adimlar:
        if notalar:
            sonuc.append((es, notalar, vurus))
            es = 0
        else:
            es += vurus
    return sonuc


def bolumlere_ayir(parcalar, uzunluk):
    bolumler = [parcalar[i:i + uzunluk] for i in range(0, len(parcalar), uzunluk)]
    # Sonda tek nota kalırsa bir önceki bölüme ekle
    if uzunluk > 1 and len(bolumler) > 1 and len(bolumler[-1]) == 1:
        bolumler[-2:] = [bolumler[-2] + bolumler[-1]]
    return bolumler


def nota_yaz(notalar):
    return " + ".join(nota_adi(n) for n in notalar)


def sure_yaz(vurus):
    return f"{vurus:g} vuruş {SURE_ADLARI.get(vurus, '')}".strip()


def sure_hatasi(calinan, beklenen):
    """Süre doğruysa None, yanlışsa açıklama döner."""
    if abs(calinan - beklenen) <= max(0.35, beklenen * 0.3):
        return None
    yon = "kısa" if calinan < beklenen else "uzun"
    return (f"vuruş {yon}: {calinan:.1f} vuruş tuttun, "
            f"beklenen {sure_yaz(beklenen)}")


def bekleme_hatasi(beklenen, olculen):
    """Notadan önceki beklemeyi denetler. beklenen=0 ise ara verilmemeli."""
    if beklenen == 0:
        if olculen > 0.6:
            return f"gereksiz bekledin: arada {olculen:.1f} vuruş boşluk var"
        return None
    if olculen < beklenen * 0.65:
        return f"es'te az bekledin: {olculen:.1f} vuruş (beklenen {beklenen:g})"
    if olculen > beklenen + max(0.6, beklenen * 0.35):
        return f"es'te fazla bekledin: {olculen:.1f} vuruş (beklenen {beklenen:g})"
    return None


class Dinleyici:
    """Kullanıcının çaldığı / yazdığı notaları ve aradaki beklemeyi ölçer."""

    def __init__(self):
        self.sifirla()

    def sifirla(self):
        self.acilis = time.monotonic()   # bundan önce basılan tuşlar sayılmaz
        self.son_birakma = None
        self.yazilan_es = 0

    def midi(self, veri, tempo):
        """(notalar, vurus, bekleme) döner. bekleme ölçülemiyorsa None."""
        notalar, saniye, baslangic = veri
        if baslangic < self.acilis:
            return None
        bekleme = None
        if self.son_birakma is not None:
            bekleme = max(0, baslangic - self.son_birakma) * tempo / 60
        self.son_birakma = baslangic + saniye
        return notalar, saniye * tempo / 60, bekleme

    def yazi(self, adimlar):
        """Yazılan adımlar; 'es' bir sonraki notanın beklemesi olur."""
        for notalar, vurus in adimlar:
            if not notalar:
                self.yazilan_es += vurus
                continue
            bekleme, self.yazilan_es = self.yazilan_es, 0
            yield notalar, vurus, bekleme


def tempo_komutu(komut, ayar):
    """Tempo komutlarını işler; komut tempo ile ilgiliyse True döner."""
    if komut == "tempolar":
        tempo_listele()
    elif komut.startswith("tempo"):
        bpm = tempo_coz(komut[5:].strip())
        if bpm:
            ayar["tempo"] = bpm
            print(f"Tempo: {bpm}  (1 vuruş = {60 / bpm:.2f} sn)")
        else:
            print(TEMPO_KULLANIM)
    else:
        return False
    return True


def yazi_coz(komut):
    try:
        return satir_coz(komut)
    except ValueError as hata:
        print(f"Anlaşılamadı: {hata}  (yardim yazabilirsin)")
        return []


# ---------------------------------------------------------- Bireysel çalışma
class Bireysel:
    """Program notayı gösterir, kullanıcı basana kadar bekler ve puanlar.

    Her notada puanlanan maddeler: doğru nota, doğru vuruş ve (öncesinde es
    varsa) doğru bekleme. Puan ilk denemeye göre verilir.
    """

    def __init__(self, parcalar):
        self.parcalar = parcalar
        self.basla()

    def basla(self):
        self.sira = 0
        self.puanlar = {}       # (sıra, madde) -> True / False
        self.hatalar = []

    @property
    def bitti_mi(self):
        return self.sira >= len(self.parcalar)

    def goster(self):
        es, notalar, vurus = self.parcalar[self.sira]
        print(f"\n[{self.sira + 1}/{len(self.parcalar)}]", end=" ")
        if es:
            print(f"Önce {es:g} vuruş BEKLE (es), sonra", end=" ")
        print(f"Bas: {nota_yaz(notalar)} | {sure_yaz(vurus)}")

    def _isle(self, madde, hata):
        """Maddenin ilk sonucunu puana yazar."""
        self.puanlar.setdefault((self.sira, madde), hata is None)
        if hata:
            ad = nota_yaz(self.parcalar[self.sira][1])
            self.hatalar.append(f"{self.sira + 1}. nota ({ad}): {hata}")
            print("  Yanlış ->", hata)

    def degerlendir(self, notalar, vurus, bekleme):
        es, beklenen, beklenen_vurus = self.parcalar[self.sira]
        ilk_deneme = (self.sira, "nota") not in self.puanlar
        if es and ilk_deneme and bekleme is not None:
            self._isle("bekleme", bekleme_hatasi(es, bekleme))
        if notalar != beklenen:
            self._isle("nota", f"yanlış nota, {nota_yaz(notalar)} bastın")
            return
        self._isle("nota", None)
        hata = sure_hatasi(vurus, beklenen_vurus)
        self._isle("vurus", hata)
        if not hata:
            print(f"  Doğru! {SURE_ADLARI.get(beklenen_vurus, 'vuruş')} tamam.")
            self.sira += 1

    def atla(self):
        maddeler = ["nota", "vurus"] + (["bekleme"] if self.parcalar[self.sira][0] else [])
        for madde in maddeler:
            self.puanlar.setdefault((self.sira, madde), False)
        self.hatalar.append(f"{self.sira + 1}. nota atlandı")
        self.sira += 1

    def puan(self):
        return round(100 * sum(self.puanlar.values()) / max(1, len(self.puanlar)))

    def karne(self):
        print("\n========== SONUÇ ==========")
        for madde, baslik in (("nota", "Doğru nota"), ("vurus", "Doğru vuruş"),
                              ("bekleme", "Doğru bekleme")):
            sonuclar = [v for (_, m), v in self.puanlar.items() if m == madde]
            if sonuclar:
                print(f"{baslik:<14}: {sum(sonuclar)}/{len(sonuclar)}")
        print(f"PUAN          : {self.puan()}/100")
        if self.hatalar:
            print("Hatalar:", *self.hatalar, sep="\n  - ")
        else:
            print("Hatasız çalışma, tebrikler!")


def bireysel_calisma(piyano, olaylar, adimlar, ayar):
    print("\n--- BİREYSEL ÇALIŞMA ---")
    print(BIREYSEL_YARDIM)
    print(f"Tempo: {ayar['tempo']}  (1 vuruş = {60 / ayar['tempo']:.2f} sn)")
    calisma = Bireysel(notalara_ayir(adimlar))
    dinleyici = Dinleyici()
    aktif = False

    def ilerle():
        nonlocal aktif
        if calisma.bitti_mi:
            calisma.karne()
            print("'bastan' ya da 'bitti' yaz.")
            aktif = False
        else:
            calisma.goster()

    while True:
        tur, veri = olaylar.get()
        if tur == "midi":
            olcum = dinleyici.midi(veri, ayar["tempo"])
            if aktif and olcum:
                once = calisma.sira
                calisma.degerlendir(*olcum)
                if calisma.sira != once or not calisma.bitti_mi:
                    ilerle()
            continue

        komut = sadelestir(veri)
        if komut in ("bitti", "menu", "cikis", "q"):
            if aktif:
                print("Çalışma yarım kaldı, puan verilmedi.")
            return
        elif komut in ("basla", "bastan"):
            calisma.basla()
            dinleyici.sifirla()
            aktif = True
            ilerle()
        elif komut == "yardim":
            print(BIREYSEL_YARDIM)
        elif tempo_komutu(komut, ayar):
            pass
        elif komut == "dinle":
            cal_ve_yaz(piyano, adimlar, ayar["tempo"])
            dinleyici.sifirla()
            if aktif:
                calisma.goster()
        elif komut in ("tekrar", "gec"):
            if not aktif:
                print("Önce 'basla' yaz.")
                continue
            if komut == "tekrar":
                _, notalar, vurus = calisma.parcalar[calisma.sira]
                piyano.cal((notalar, vurus), ayar["tempo"])
            else:
                calisma.atla()
            dinleyici.sifirla()
            ilerle()
        elif komut:
            if not aktif:
                print("Önce 'basla' yaz.")
                continue
            for olcum in dinleyici.yazi(yazi_coz(komut)):
                calisma.degerlendir(*olcum)
                ilerle()
                if not aktif:
                    break


# ---------------------------------------------------------- Tekrarlı solfej
def cal_ve_yaz(piyano, adimlar, tempo):
    print("Dinle..." if piyano.cikis else "(MIDI çıkış yok, yalnızca yazdırılıyor)")
    for adim in adimlar:
        print("  ", adim_yaz(adim))
        piyano.cal(adim, tempo)


def bolum_degerlendir(bolum, calinan):
    """Kullanıcının tekrarını bölümle karşılaştırır, hata listesi döner."""
    hatalar = []
    for i, ((es, notalar, vurus), (basilan, sure, bekleme)) in enumerate(zip(bolum, calinan)):
        sorunlar = []
        # İlk notadan önceki bekleme ölçülmez
        if i and bekleme is not None:
            sorunlar.append(bekleme_hatasi(es, bekleme))
        if basilan != notalar:
            sorunlar.append(f"yanlış nota, {nota_yaz(basilan)} bastın")
        sorunlar.append(sure_hatasi(sure, vurus))
        hatalar += [f"{i + 1}. nota ({nota_yaz(notalar)}): {s}" for s in sorunlar if s]
    return hatalar


def tekrarli_solfej(piyano, olaylar, adimlar, ayar):
    print("\n--- TEKRARLI SOLFEJ ---")
    print("Önce ben bir bölüm çalacağım. Bitince aynısını sen çal.")
    print(TEKRARLI_YARDIM)
    parcalar = notalara_ayir(adimlar)
    bolumler = bolumlere_ayir(parcalar, BOLUM_UZUNLUGU)
    dinleyici = Dinleyici()
    sira = 0
    aktif = False
    calinan = []

    def sun():
        """Sıradaki bölümü çalar, sonra kullanıcıyı dinlemeye başlar."""
        bolum = bolumler[sira]
        dizi = []
        for i, (es, notalar, vurus) in enumerate(bolum):
            if es and i:
                dizi.append(((), es))
            dizi.append((notalar, vurus))
        print(f"\n=== Bölüm {sira + 1}/{len(bolumler)} ===")
        time.sleep(60 / ayar["tempo"])
        cal_ve_yaz(piyano, dizi, ayar["tempo"])
        calinan.clear()
        dinleyici.sifirla()
        print(f"ŞİMDİ SIRA SENDE: {len(bolum)} nota çal.")

    def al(olcum):
        """Bir notayı kaydeder; bölüm tamamlanınca değerlendirir."""
        nonlocal sira, aktif
        calinan.append(olcum)
        print(f"  {len(calinan)}/{len(bolumler[sira])}: {nota_yaz(olcum[0])}")
        if len(calinan) < len(bolumler[sira]):
            return False
        hatalar = bolum_degerlendir(bolumler[sira], calinan)
        if hatalar:
            print("Yanlışlar:", *hatalar, sep="\n  - ")
            print("Aynı bölümü tekrar dinle.")
        else:
            print("Harika, bölüm doğru!")
            sira += 1
        if sira < len(bolumler):
            sun()
        else:
            print("\nTüm bölümler tamamlandı. 'bastan' ya da 'bitti' yaz.")
            aktif = False
        return True

    while True:
        tur, veri = olaylar.get()
        if tur == "midi":
            olcum = dinleyici.midi(veri, ayar["tempo"])
            if aktif and olcum:
                al(olcum)
            continue

        komut = sadelestir(veri)
        if komut in ("bitti", "menu", "cikis", "q"):
            return
        elif komut in ("basla", "bastan"):
            sira, aktif = 0, True
            sun()
        elif komut == "yardim":
            print(TEKRARLI_YARDIM)
        elif tempo_komutu(komut, ayar):
            pass
        elif komut.startswith("bolum"):
            sayi = komut[5:].strip()
            if sayi.isdecimal() and 1 <= int(sayi) <= 16:
                bolumler = bolumlere_ayir(parcalar, int(sayi))
                aktif = False
                print(f"Bölüm uzunluğu {sayi} nota. Başlamak için 'basla' yaz.")
            else:
                print("Kullanım: bolum 1-16")
        elif komut in ("tekrar", "dinle", "gec"):
            if not aktif:
                print("Önce 'basla' yaz.")
                continue
            if komut == "gec":
                sira += 1
            if sira < len(bolumler):
                sun()
            else:
                print("\nSon bölüm geçildi. 'bastan' ya da 'bitti' yaz.")
                aktif = False
        elif komut:
            if not aktif:
                print("Önce 'basla' yaz.")
                continue
            for olcum in dinleyici.yazi(yazi_coz(komut)):
                if al(olcum):       # bölüm bitti, satırın kalanı sayılmaz
                    break


def solfej_modu(piyano, olaylar):
    gunun = SOLFEJLER[datetime.date.today().toordinal() % len(SOLFEJLER)]
    print(f'günün solfej çalışması = "{gunun}"')
    print(*piyano.durum, sep="\n")
    adimlar = satir_coz(gunun)
    ayar = {"tempo": VARSAYILAN_TEMPO}
    calismalar = {"1": tekrarli_solfej, "2": bireysel_calisma}
    while True:
        print("\nSOLFEJ MENÜSÜ\n1) Tekrarlı solfej\n2) Bireysel çalışma\n"
              "q) Ana menü\nSeçimin:")
        tur, veri = olaylar.get()
        while tur != "yazi":
            tur, veri = olaylar.get()
        secim = sadelestir(veri)
        if secim in ("q", "bitti", "menu", "cikis"):
            return
        if secim in calismalar:
            calismalar[secim](piyano, olaylar, adimlar, ayar)
        else:
            print("1, 2 ya da q yaz.")


# ------------------------------------------------------------------ 3) TON, AKOR VE GAM
# İlk seviye: aynı donanımı paylaşan iki majör-minör çifti.
# kok: gamın başladığı MIDI notası. melodi: kök seste biten kısa örnek.
TONLAR = {
    "C majör": {"kok": 60, "tur": "major", "donanim": "diyez ya da bemol yok",
                "melodi": "do mi sol fa mi re do:2"},
    "A minör": {"kok": 69, "tur": "minor", "donanim": "diyez ya da bemol yok",
                "melodi": "la do5 mi5 re5 do5 si la:2"},
    "F majör": {"kok": 65, "tur": "major", "donanim": "1 bemol (sib)",
                "melodi": "fa la do5 sib la sol fa:2"},
    "D minör": {"kok": 62, "tur": "minor", "donanim": "1 bemol (sib)",
                "melodi": "re fa la sol fa mi re:2"},
}
GAM_ARALIKLARI = {"major": (0, 2, 4, 5, 7, 9, 11, 12),
                  "minor": (0, 2, 3, 5, 7, 8, 10, 12)}
AKOR_ARALIKLARI = {"major": (0, 4, 7), "minor": (0, 3, 7)}
TUR_ADI = {"major": "majör", "minor": "minör"}
KOK_HARFLERI = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11, **NOTALAR}
TON_DESENI = re.compile(r"^(do|re|mi|fa|sol|la|si|[a-g])\s*(major|maj|minor|min|m)$")

KAVRAMLAR = """
--- TEMEL KAVRAMLAR ---
Harf adları : C=do  D=re  E=mi  F=fa  G=sol  A=la  B=si
Yarım ses   : bir tuştan hemen yanındaki tuşa (siyah ya da beyaz) olan mesafe.
              Tam ses = 2 yarım ses.
Diyez (#)   : sesi yarım ses inceltir (hemen sağdaki tuş).
Bemol (b)   : sesi yarım ses kalınlaştırır (hemen soldaki tuş). sib = si bemol
Donanım     : bir tonda sürekli kullanılan diyez ve bemoller.
Ton         : parçanın merkez sesi ve kullandığı gam.
Majör       : çoğunlukla daha parlak duyulur.
              Gam: T T Y T T T Y   Akor: 4 + 3 yarım ses
Minör       : çoğunlukla daha hüzünlü duyulur.
              Doğal gam: T Y T T Y T T   Akor: 3 + 4 yarım ses
              (T = tam ses, Y = yarım ses)

Aynı donanımı bir majör ve bir minör ton paylaşır (C majör / A minör,
F majör / D minör). Ayırmak için merkez sese bak: parça çoğunlukla orada biter.
Not: Ton ile başlangıç notası aynı şey değildir. D minör bir parça la ya da
fa ile de başlayabilir. Gam ise kök sesten (D minörde re) başlar."""


def perde_adi(numara, bemol):
    """Oktavsız nota adı; bemollü tonlarda la# yerine sib yazar."""
    ad = ADLAR[numara % 12]
    if bemol and "#" in ad:
        return ADLAR[(numara + 1) % 12] + "b"
    return ad


def ton_bilgisi(ad):
    ton = TONLAR[ad]
    bemol = "bemol (" in ton["donanim"]
    gam = [ton["kok"] + a for a in GAM_ARALIKLARI[ton["tur"]]]
    akor = [ton["kok"] + a for a in AKOR_ARALIKLARI[ton["tur"]]]
    return {**ton, "ad": ad, "bemol": bemol, "gam": gam, "akor": akor,
            "kok_adi": perde_adi(ton["kok"], bemol),
            "gam_adlari": " ".join(perde_adi(n, bemol) for n in gam),
            "akor_adlari": " + ".join(perde_adi(n, bemol) for n in akor)}


def ton_coz(metin):
    """'d minör', 're minor', 'Dm' -> (kök perdesi, tür). Anlaşılmazsa None."""
    eslesme = TON_DESENI.match(sadelestir(metin))
    if not eslesme:
        return None
    kok, tur = eslesme.groups()
    return KOK_HARFLERI[kok], "major" if tur.startswith("maj") else "minor"


def ton_dogru(cevap, ton):
    return cevap == (ton["kok"] % 12, ton["tur"])


def yazi_bekle(olaylar):
    """Terminalden bir satır bekler; bu sırada basılan tuşları yok sayar."""
    while True:
        tur, veri = olaylar.get()
        if tur == "yazi":
            return sadelestir(veri)


def notalari_bekle(olaylar, dinleyici):
    """Piyanodan ya da klavyeden gelen girişi bekler.

    ("komut", yazi) ya da ("notalar", [nota grubu, ...]) döner.
    """
    while True:
        tur, veri = olaylar.get()
        if tur == "midi":
            olcum = dinleyici.midi(veri, VARSAYILAN_TEMPO)
            if olcum:
                return "notalar", [olcum[0]]
            continue
        komut = sadelestir(veri)
        try:
            gruplar = [n for n, _ in satir_coz(komut) if n]
        except ValueError:
            gruplar = []
        if gruplar:
            return "notalar", gruplar
        if komut:
            return "komut", komut


def melodi_cal(piyano, ton):
    if not piyano.cikis:
        print("(MIDI çıkış yok, melodi çalınamıyor)")
        return
    print("Melodi çalınıyor...")
    for adim in satir_coz(ton["melodi"]):
        piyano.cal(adim, VARSAYILAN_TEMPO)


# ---------------------------------------------------------- Öğren
def ton_anlat(piyano, ton):
    print(f"\n=== {ton['ad']} ===")
    print(f"Donanım   : {ton['donanim']}")
    print(f"Merkez ses: {ton['kok_adi']}")
    formul = "T T Y T T T Y" if ton["tur"] == "major" else "T Y T T Y T T"
    print(f"Gam       : {ton['gam_adlari']}   ({formul})")
    araliklar = "4 + 3" if ton["tur"] == "major" else "3 + 4"
    print(f"Akor      : {ton['akor_adlari']}   ({araliklar} yarım ses)")
    print(f"Başlangıç : gamı {ton['kok_adi']} ile başlat ve {ton['kok_adi']} ile bitir.")
    if piyano.cikis:
        print("Dinle: önce gam, sonra akor, sonra örnek melodi.")
        for nota in ton["gam"]:
            piyano.cal(((nota,), 1), VARSAYILAN_TEMPO)
        piyano.cal((tuple(ton["akor"]), 2), VARSAYILAN_TEMPO)
        melodi_cal(piyano, ton)


def ton_ogren(piyano, olaylar):
    gunun = list(TONLAR)[datetime.date.today().toordinal() % len(TONLAR)]
    print(f'günün tonu = "{gunun}"')
    print(KAVRAMLAR)
    yardim = (f"\nBir ton yaz ({', '.join(TONLAR)}) ya da: "
              "gunun, kavramlar, bitti")
    print(yardim)
    while True:
        komut = yazi_bekle(olaylar)
        if komut in ("bitti", "q", "menu", "cikis"):
            return
        if komut == "kavramlar":
            print(KAVRAMLAR)
        elif komut == "gunun":
            ton_anlat(piyano, ton_bilgisi(gunun))
        else:
            cevap = ton_coz(komut)
            ad = next((a for a in TONLAR if ton_dogru(cevap, ton_bilgisi(a))), None)
            if ad:
                ton_anlat(piyano, ton_bilgisi(ad))
        print(yardim)


# ---------------------------------------------------------- Yardımlı ve puanlı
def soru_goster(ton, no, toplam):
    """Yalnızca tonu bulmaya yetecek bilgiler gösterilir."""
    print(f"\n=== Soru {no}/{toplam} ===")
    print(f"Donanım               : {ton['donanim']}")
    print(f"Melodinin son notası  : {ton['kok_adi']}")


def ipuclari(ton):
    adaylar = [a for a, t in TONLAR.items() if t["donanim"] == ton["donanim"]]
    return [
        f"Bu donanımın iki adayı var: {' ve '.join(adaylar)}.",
        f"Merkez ses çoğunlukla son notadır: {ton['kok_adi']}.",
        f"{ton['kok_adi']} üzerindeki akor {ton['akor_adlari']}; "
        "aradaki yarım sesleri say (4+3 majör, 3+4 minör).",
        f"Cevap {ton['ad']}. Gam: {ton['gam_adlari']}",
    ]


def aciklama(ton):
    adaylar = [a for a, t in TONLAR.items() if t["donanim"] == ton["donanim"]]
    return (f"Neden? Donanım ({ton['donanim']}) {' ya da '.join(adaylar)} demek; "
            f"melodi {ton['kok_adi']} sesinde bittiği için {ton['ad']}.\n"
            f"Doğru gam: {ton['gam_adlari']}")


def yardimli_alistirma(piyano, olaylar):
    print("\n--- YARDIMLI ALIŞTIRMA (puansız) ---")
    print("Komutlar: ipucu, dinle, gec, bitti")
    sorular = random.sample(list(TONLAR), len(TONLAR))
    dinleyici = Dinleyici()
    for no, ad in enumerate(sorular, 1):
        ton = ton_bilgisi(ad)
        hazir_ipucu = ipuclari(ton)
        verilen = 0
        soru_goster(ton, no, len(sorular))
        print("Bu hangi ton? (ör: C majör)")
        ton_bulundu = False
        sira = 0
        dinleyici.sifirla()
        while sira < len(ton["gam"]):
            if ton_bulundu:
                tur, veri = notalari_bekle(olaylar, dinleyici)
            else:
                tur, veri = "komut", yazi_bekle(olaylar)
            if tur == "komut":
                if veri in ("bitti", "q", "menu", "cikis"):
                    return
                if veri == "gec":
                    print(aciklama(ton))
                    break
                if veri == "ipucu":
                    print("İpucu:", hazir_ipucu[min(verilen, len(hazir_ipucu) - 1)])
                    verilen += 1
                elif veri == "dinle":
                    melodi_cal(piyano, ton)
                    dinleyici.sifirla()
                elif ton_bulundu:
                    print("Notayı çal/yaz ya da: ipucu, dinle, gec, bitti")
                elif ton_coz(veri) is None:
                    print("Tonu 're minör' ya da 'Dm' gibi yaz.")
                elif ton_dogru(ton_coz(veri), ton):
                    ton_bulundu = True
                    dinleyici.sifirla()
                    print(f"Doğru, {ad}! Şimdi gamı kök sesinden başlayarak çal (8 nota).")
                else:
                    print("Bu değil. Tekrar dene ya da 'ipucu' yaz.")
                continue
            for grup in veri:
                if sira >= len(ton["gam"]):
                    break
                if len(grup) == 1 and grup[0] % 12 == ton["gam"][sira] % 12:
                    sira += 1
                    print(f"  {sira}/8 doğru: {perde_adi(grup[0], ton['bemol'])}")
                else:
                    basilan = " + ".join(perde_adi(n, ton["bemol"]) for n in grup)
                    print(f"  {basilan} değil, {sira + 1}. notayı tekrar dene.")
                    break
        else:
            print(f"Tebrikler, {ad} gamını tamamladın.")
    print("\nAlıştırma bitti. Hazırsan puanlı sınavı dene.")


def soru_puani(ton, cevap, calinan):
    """(ton puanı /30, başlangıç puanı /20, gam puanı /50)"""
    dogrular = sum(len(g) == 1 and g[0] % 12 == n % 12
                   for g, n in zip(calinan, ton["gam"]))
    baslangic = len(calinan[0]) == 1 and calinan[0][0] % 12 == ton["kok"] % 12
    return (30 if ton_dogru(cevap, ton) else 0,
            20 if baslangic else 0,
            round(50 * dogrular / len(ton["gam"])))


def puanli_sinav(piyano, olaylar):
    print("\n--- PUANLI SINAV ---")
    print("Her soruda: önce tonu yaz, sonra gamı kök sesinden başlayarak çal (8 nota).")
    print("İlk cevabın sayılır, oktav önemli değil. Komutlar: dinle, bitti")
    sorular = random.sample(list(TONLAR), len(TONLAR))
    dinleyici = Dinleyici()
    puanlar = []
    for no, ad in enumerate(sorular, 1):
        ton = ton_bilgisi(ad)
        soru_goster(ton, no, len(sorular))
        print("Bu hangi ton?")
        cevap = None
        while cevap is None:
            komut = yazi_bekle(olaylar)
            if komut in ("bitti", "q", "menu", "cikis"):
                print("Sınav yarım kaldı, puan verilmedi.")
                return
            if komut == "dinle":
                melodi_cal(piyano, ton)
                continue
            cevap = ton_coz(komut)
            if cevap is None:
                print("Tonu 'nota adı + majör/minör' biçiminde yaz.")
        print("Şimdi gamı çal:")
        calinan = []
        dinleyici.sifirla()
        while len(calinan) < len(ton["gam"]):
            tur, veri = notalari_bekle(olaylar, dinleyici)
            if tur == "komut":
                if veri in ("bitti", "q", "menu", "cikis"):
                    print("Sınav yarım kaldı, puan verilmedi.")
                    return
                if veri == "dinle":
                    melodi_cal(piyano, ton)
                    dinleyici.sifirla()
                else:
                    print("Notayı çal/yaz ya da: dinle, bitti")
                continue
            for grup in veri[:len(ton["gam"]) - len(calinan)]:
                calinan.append(grup)
                basilan = " + ".join(perde_adi(n, ton["bemol"]) for n in grup)
                print(f"  {len(calinan)}/8: {basilan}")
        t, b, g = soru_puani(ton, cevap, calinan)
        puanlar.append(t + b + g)
        print(f"\nTon {t}/30 | Başlangıç {b}/20 | Gam {g}/50 | Toplam {t + b + g}/100")
        print(aciklama(ton))
    print(f"\n========== SINAV PUANI: {round(sum(puanlar) / len(puanlar))}/100 ==========")


# ---------------------------------------------------------- Akor ve kulak
def akoru_bas(piyano, olaylar):
    print("\n--- AKORU BAS ---")
    print("Söylenen akorun üç sesini birlikte bas (yazarak: do+mi+sol).")
    print("Her oktav ve çevrim kabul edilir. Komutlar: ipucu, gec, bitti")
    sorular = random.sample(list(TONLAR), len(TONLAR))
    dinleyici = Dinleyici()
    dogru = 0
    # Tuşlar tek tek basılsa da hepsi bırakılana kadar aynı akor sayılsın
    piyano.akor_penceresi(float("inf"))
    try:
        for no, ad in enumerate(sorular, 1):
            ton = ton_bilgisi(ad)
            hedef = {n % 12 for n in ton["akor"]}
            ilk = True
            print(f"\n{no}/{len(sorular)}: {ad} akorunu bas")
            dinleyici.sifirla()
            while True:
                tur, veri = notalari_bekle(olaylar, dinleyici)
                if tur == "komut":
                    if veri in ("bitti", "q", "menu", "cikis"):
                        return
                    if veri == "ipucu":
                        ilk = False
                        aralik = "4 + 3" if ton["tur"] == "major" else "3 + 4"
                        print(f"Kök ses {ton['kok_adi']}, {TUR_ADI[ton['tur']]}: "
                              f"{aralik} yarım ses.")
                    elif veri == "gec":
                        print("Cevap:", ton["akor_adlari"])
                        break
                    else:
                        print("Akoru çal/yaz ya da: ipucu, gec, bitti")
                    continue
                if {n % 12 for n in veri[0]} == hedef:
                    dogru += ilk
                    print("Doğru!", ton["akor_adlari"])
                    break
                ilk = False
                basilan = " + ".join(perde_adi(n, ton["bemol"]) for n in veri[0])
                print(f"Olmadı ({basilan}). Tekrar dene.")
        print(f"\nPUAN: {round(100 * dogru / len(sorular))}/100 "
              "(ilk denemede ipucusuz doğrular)")
    finally:
        piyano.akor_penceresi(AKOR_PENCERESI)


def kulak_egitimi(piyano, olaylar, soru_sayisi=8):
    print("\n--- KULAK EĞİTİMİ ---")
    if not piyano.cikis:
        print("Bu çalışma için piyanonun MIDI çıkışı bağlı olmalı.")
        return
    print("Akoru dinle, 'major' ya da 'minor' yaz. Komutlar: tekrar, bitti")
    dogru = 0
    for no in range(1, soru_sayisi + 1):
        tur = random.choice(list(AKOR_ARALIKLARI))
        kok = random.choice([t["kok"] for t in TONLAR.values()])
        adim = (tuple(kok + a for a in AKOR_ARALIKLARI[tur]), 2)
        print(f"\n{no}/{soru_sayisi}: Majör mü, minör mü?")
        piyano.cal(adim, VARSAYILAN_TEMPO)
        while True:
            cevap = yazi_bekle(olaylar)
            if cevap in ("bitti", "q", "menu", "cikis"):
                return
            if cevap == "tekrar":
                piyano.cal(adim, VARSAYILAN_TEMPO)
            elif cevap in ("major", "minor"):
                break
            else:
                print("'major', 'minor', 'tekrar' ya da 'bitti' yaz.")
        dogru += cevap == tur
        print("Doğru!" if cevap == tur else f"Yanlış, bu {TUR_ADI[tur]} akordu.")
    print(f"\nPUAN: {round(100 * dogru / soru_sayisi)}/100")


def ton_modu(piyano, olaylar):
    calismalar = {"1": ton_ogren, "2": yardimli_alistirma, "3": puanli_sinav,
                  "4": akoru_bas, "5": kulak_egitimi}
    print(*piyano.durum, sep="\n")
    while True:
        print("\nTON, AKOR VE GAM\n1) Öğren\n2) Yardımlı alıştırma\n3) Puanlı sınav\n"
              "4) Akoru bas\n5) Kulak eğitimi\nq) Ana menü\nSeçimin:")
        secim = yazi_bekle(olaylar)
        if secim in ("q", "bitti", "menu", "cikis"):
            return
        if secim in calismalar:
            bosalt(olaylar)
            calismalar[secim](piyano, olaylar)
        else:
            print("1-5 ya da q yaz.")


# ------------------------------------------------------------------ ANA PROGRAM
def klavye_oku(olaylar):
    """Terminalden yazılanları olay kuyruğuna koyar."""
    while True:
        try:
            olaylar.put(("yazi", input()))
        except EOFError:
            break
    while True:                 # giriş kapandıysa tüm menülerden çık
        if olaylar.empty():
            olaylar.put(("yazi", "cikis"))
        time.sleep(0.1)


def bosalt(olaylar):
    """Mod başlamadan önce piyanoda basılmış tuşları yok sayar."""
    bekleyen = []
    while not olaylar.empty():
        olay = olaylar.get()
        if olay[0] == "yazi":
            bekleyen.append(olay)
    for olay in bekleyen:
        olaylar.put(olay)


def main():
    ayristirici = argparse.ArgumentParser(description="Beste, solfej ve ton çalışması")
    ayristirici.add_argument("mod", nargs="?", choices=["1", "2", "3", "portlar"])
    ayristirici.add_argument("--port", default="", help="MIDI port adının bir parçası")
    secenek = ayristirici.parse_args()

    if secenek.mod == "portlar":
        if mido is None:
            print("Önce: pip install mido python-rtmidi")
        else:
            print("Girişler:", mido.get_input_names())
            print("Çıkışlar:", mido.get_output_names())
        return

    olaylar = queue.Queue()
    piyano = Piyano(olaylar, secenek.port)
    threading.Thread(target=klavye_oku, args=(olaylar,), daemon=True).start()
    modlar = {"1": beste_modu, "2": solfej_modu, "3": ton_modu}
    secim = secenek.mod
    try:
        while True:
            if secim is None:
                print("\n1) Beste oluştur\n2) Solfej pratiği\n3) Ton, akor ve gam\nq) Çıkış\nSeçimin:")
                tur, veri = olaylar.get()
                while tur != "yazi":
                    tur, veri = olaylar.get()
                secim = sadelestir(veri)
            if secim in ("q", "cikis"):
                break
            if secim in modlar:
                bosalt(olaylar)
                modlar[secim](piyano, olaylar)
            else:
                print("1, 2, 3 ya da q yaz.")
            secim = None
    except KeyboardInterrupt:
        print("\nÇıkılıyor.")
    finally:
        piyano.kapat()


if __name__ == "__main__":
    main()
