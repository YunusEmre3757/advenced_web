import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

import { AuthApi } from './auth-api';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthApi);
  const router = inject(Router);
  if (auth.isAuthenticated()) return true;
  router.navigate(['/login']);
  return false;
};
