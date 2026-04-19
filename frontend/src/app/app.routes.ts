import { Routes } from '@angular/router';
import { Dashboard } from './pages/dashboard/dashboard';
import { Map } from './pages/map/map';
import { Login } from './pages/login/login';
import { Register } from './pages/register/register';
import { Profile } from './pages/profile/profile';
import { Safety } from './pages/safety/safety';
import { SafetyGuide } from './pages/safety-guide/safety-guide';
import { AiAssistant } from './pages/ai-assistant/ai-assistant';
import { BuildingRisk } from './pages/building-risk/building-risk';
import { HistoricalMap } from './pages/historical-map/historical-map';
import { HeatmapPage } from './pages/heatmap/heatmap';
import { EarthquakeDetailPage } from './pages/earthquake-detail/earthquake-detail';
import { authGuard } from './core/auth.guard';

export const routes: Routes = [
    { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    { path: 'login', component: Login },
    { path: 'register', component: Register },
    { path: 'profile', component: Profile, canActivate: [authGuard] },
    { path: 'safety', component: Safety, canActivate: [authGuard] },
    { path: 'safety-guide', component: SafetyGuide },
    { path: 'ai-assistant', component: AiAssistant },
    { path: 'building-risk', component: BuildingRisk },
    { path: 'historical-map', component: HistoricalMap },
    { path: 'heatmap', component: HeatmapPage },
    { path: 'dashboard', component: Dashboard },
    { path: 'map', component: Map },
    { path: 'earthquakes/:id', component: EarthquakeDetailPage },
    { path: 'risk-query', redirectTo: 'building-risk', pathMatch: 'full' },
    { path: '**', redirectTo: 'dashboard' } // Bilinmeyen linkte ana sayfaya dön
];
