import { Component, signal } from '@angular/core';

interface GuideStep {
  title: string;
  body: string;
}

interface GuideSection {
  id: string;
  label: string;
  heading: string;
  description: string;
  steps: GuideStep[];
}

@Component({
  selector: 'app-safety-guide',
  standalone: true,
  imports: [],
  templateUrl: './safety-guide.html',
  styleUrl: './safety-guide.css',
})
export class SafetyGuide {
  readonly sections: GuideSection[] = [
    {
      id: 'before',
      label: 'Oncesi',
      heading: 'Deprem oncesi hazirlik',
      description: 'Evde ve isyerinde yapilacak sade kontroller buyuk farklar yaratir.',
      steps: [
        {
          title: 'Agir esyalari sabitle',
          body: 'Gardirop, kitaplik, televizyon ve buzdolabini duvara veya zemine sabitle. Yataklarin ustune agir tablo/raf asma.'
        },
        {
          title: 'Kacis rotani belirle',
          body: 'Her odadan disariya cikis yolunu not al. Apartmanda merdiveni, is yerinde acil toplanma noktasini ogren.'
        },
        {
          title: 'Deprem cantasi hazirla',
          body: 'Kisi basi 3 gunluk su, uzun omurlu gida, ilk yardim seti, dudukle, fener, pilli radyo, nakit, ilaclar, bebek/evcil hayvan ihtiyaclari.'
        },
        {
          title: 'Aile iletisim plani',
          body: 'Sehir disindan bir ortak irtibat kisisi belirle. Herkes ayni numarayi bilsin. Toplanma noktasini konus.'
        },
        {
          title: 'Kritik belgelerin kopyasi',
          body: 'Kimlik, tapu, sigorta, saglik raporlarinin dijital kopyasini cantada ve bulutta tut.'
        }
      ]
    },
    {
      id: 'during',
      label: 'Ani',
      heading: 'Deprem sirasinda',
      description: 'Ilk saniyede karar ver: kalici esyadan uzak, saglam bir noktada kal.',
      steps: [
        {
          title: 'COK - CEK - KAL',
          body: 'Yere cok, saglam bir masa/mobilya altina cek, sarsinti bitene kadar orada kal. Bas ve boynunu koru.'
        },
        {
          title: 'Pencere ve disardan dusebilecek esya yok',
          body: 'Cam, ayna, avize, kitaplik, dolap, televizyon yanindan uzaklas. Ic duvar dibi daha guvenli.'
        },
        {
          title: 'Ic mekanda kal',
          body: 'Sarsinti sirasinda disari kosma. Merdiven ve asansor kullanma. Balkon ve sundurma cokebilir.'
        },
        {
          title: 'Disaridaysan',
          body: 'Binalardan, direklerden, elektrik hatlarindan uzaklas. Acik alanda yere cok, basini koru.'
        },
        {
          title: 'Araclaysan',
          body: 'Guvenli sekilde kenara cek, motoru kapat, kemerini takili tut. Ust gecit, koprii, agac altindan uzak dur.'
        },
        {
          title: 'Tekerlekli sandalye',
          body: 'Frenleri kilitle. Bas ve boynunu kol veya yastikla koru. Sarsinti bittiginde guvenli alana gec.'
        }
      ]
    },
    {
      id: 'after',
      label: 'Sonrasi',
      heading: 'Deprem sonrasi ilk saatler',
      description: 'Artcilar gelebilir. Panikle hareket etme, sira ile kontrol et.',
      steps: [
        {
          title: 'Kendini ve yakindakileri kontrol et',
          body: 'Yaralanma var mi bak. Agir yaralananlari hareket ettirme, 112 cagir. Kanamayi baski ile durdur.'
        },
        {
          title: 'Gaz, su, elektrik',
          body: 'Gaz sizintisi kokusu varsa vanayi kapat, pencereyi ac, elektrik dugmesine basma. Su ve elektrigi gerektiginde kapat.'
        },
        {
          title: 'Binadan dikkatle cik',
          body: 'Cati, merdiven, kapi cercevelerine dikkat. Asansor kullanma. Anahtar, telefon, cantayi al.'
        },
        {
          title: 'Toplanma noktasina git',
          body: 'Mahallenin belirlenmis toplanma alanina gec. Aile uyelerini bekle, Guvendeyim akisi ile durumu aileye bildir.'
        },
        {
          title: 'Telefon trafigi yogun',
          body: 'Sesli arama yerine SMS veya uygulama mesaji kullan. Hat acik kalmasi icin kisa mesaj yaz.'
        },
        {
          title: 'Dogrulanmamis haberlere kapilma',
          body: 'AFAD ve Kandilli resmi kanallarini takip et. Sosyal medya soylentisini paylasmadan once dogrula.'
        }
      ]
    },
    {
      id: 'kit',
      label: 'Canta',
      heading: 'Deprem cantasi kontrol listesi',
      description: 'Cantayi yilda iki kez kontrol et, son kullanma tarihlerini yenile.',
      steps: [
        { title: 'Su', body: 'Kisi basi gunluk 2 litre, en az 3 gunluk stok.' },
        { title: 'Gida', body: 'Konserve, kuruyemis, enerji bari, bebek mamasi. Konserve acacagi unutulmasin.' },
        { title: 'Ilk yardim', body: 'Steril gazli bez, yara bandi, antiseptik, agri kesici, kronik hastalik ilaci, maske.' },
        { title: 'Isik ve iletisim', body: 'Pilli fener, yedek pil, powerbank, pilli radyo, duduk.' },
        { title: 'Belge ve nakit', body: 'Kimlik/tapu/sigorta fotokopisi, kucuk banknot, bozuk para.' },
        { title: 'Kisisel', body: 'Yedek gozluk, hijyen malzemesi, kadin pedi, bebek bezi, termal battaniye, yagmurluk.' }
      ]
    }
  ];

  readonly activeId = signal<string>(this.sections[0].id);

  setActive(id: string): void {
    this.activeId.set(id);
  }

  isActive(id: string): boolean {
    return this.activeId() === id;
  }

  activeSection(): GuideSection {
    return this.sections.find(s => s.id === this.activeId()) ?? this.sections[0];
  }
}
