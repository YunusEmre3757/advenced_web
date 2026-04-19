import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AiApi, GraphChatResponse } from '../../core/ai-api';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  category?: string;
  sources?: string[];
}

@Component({
  selector: 'app-ai-assistant',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './ai-assistant.html',
  styleUrl: './ai-assistant.css',
})
export class AiAssistant implements OnDestroy {
  private readonly api = inject(AiApi);
  private readonly sessionId = `ai-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`;
  private closeStream: (() => void) | null = null;

  readonly messages = signal<Message[]>([
    {
      role: 'assistant',
      text: 'Merhaba. Son depremleri, guvenlik rehberini veya bolge riskini sorabilirsin.',
      category: 'smalltalk',
    },
  ]);
  readonly input = signal('');
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly userLat = signal<number | null>(null);
  readonly userLng = signal<number | null>(null);

  readonly suggestions = [
    'Son 24 saatte Turkiye\'de kac deprem oldu?',
    'Depreme nasil hazirlanmaliyim?',
    'Benim bolgemde risk var mi?',
  ];

  askSuggestion(q: string): void {
    this.input.set(q);
    this.send();
  }

  captureLocation(): void {
    if (!('geolocation' in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      pos => {
        this.userLat.set(pos.coords.latitude);
        this.userLng.set(pos.coords.longitude);
      },
      () => {}
    );
  }

  send(): void {
    const q = this.input().trim();
    if (!q || this.loading()) return;
    this.input.set('');
    this.error.set(null);
    this.messages.update(m => [...m, { role: 'user', text: q }]);
    const assistantIndex = this.messages().length;
    this.messages.update(m => [...m, {
      role: 'assistant',
      text: '',
      category: 'smalltalk',
      sources: [],
    }]);
    this.loading.set(true);

    const ctx: { latitude?: number; longitude?: number } = {};
    const lat = this.userLat();
    const lng = this.userLng();
    if (lat !== null && lng !== null) {
      ctx.latitude = lat;
      ctx.longitude = lng;
    }

    this.closeStream?.();
    this.closeStream = this.api.streamGraphChat(
      { question: q, sessionId: this.sessionId, userContext: ctx },
      {
        meta: (meta) => {
          this.messages.update(m => m.map((msg, idx) =>
            idx === assistantIndex ? { ...msg, category: meta.category, sources: meta.sources } : msg
          ));
        },
        token: (token) => {
          this.messages.update(m => m.map((msg, idx) =>
            idx === assistantIndex ? { ...msg, text: msg.text + token } : msg
          ));
        },
        done: (res: GraphChatResponse) => {
          this.messages.update(m => m.map((msg, idx) =>
            idx === assistantIndex ? {
              ...msg,
              text: res.answer,
              category: res.category,
              sources: res.sources,
            } : msg
          ));
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.error.set('AI servisine ulasilamadi. LangGraph servisi (port 8002) calisiyor mu?');
        },
      });
  }

  ngOnDestroy(): void {
    this.closeStream?.();
  }

  categoryLabel(cat?: string): string {
    switch (cat) {
      case 'data': return 'Veri';
      case 'guide': return 'Rehber';
      case 'risk': return 'Risk';
      case 'smalltalk': return 'Sohbet';
      default: return '';
    }
  }
}
