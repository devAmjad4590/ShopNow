package com.shopnow.auth_service.auth;

import com.shopnow.auth_service.jwt.JWTService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/auth")
public class AuthController {
    private final AuthService authService;

    @PostMapping("/register")
    public ResponseEntity<RegistrationResponse> registerUser(@RequestBody @Valid RegistrationRequest req){
        return ResponseEntity.ok(authService.registerUser(req));
    }

    @PostMapping("/login")
    public ResponseEntity<LoginResponse> loginUser(@RequestBody @Valid LoginRequest req){
        LoginResponse loginResponse = authService.loginUser(req);

        ResponseCookie responseCookie = createRefreshTokenCookie(loginResponse.getRefresh_token());

        loginResponse.setRefresh_token(null);

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, responseCookie.toString())
                .body(loginResponse);
    }

    @PostMapping("/refresh")
    public ResponseEntity<RefreshResponse> refresh(@CookieValue(name = "refresh_token", required = false)
                                                       String refreshToken){
        if (refreshToken == null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
        }

        RefreshResponse response = authService.refresh(refreshToken);

        ResponseCookie cookie = createRefreshTokenCookie(response.getRefreshToken());
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body(response);

    }


    private ResponseCookie createRefreshTokenCookie(String token){
        return ResponseCookie.from("refresh_token", token)
                .httpOnly(true)
                .secure(true)
                .path("/auth")
                .maxAge(7 * 24 * 60 * 60)
                .sameSite("Strict")
                .build();
    }

}
