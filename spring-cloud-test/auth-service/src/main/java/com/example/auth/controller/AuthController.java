package com.example.auth.controller;

import com.example.auth.dto.LoginRequest;
import com.example.auth.service.AuthService;
import java.util.Map;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class AuthController {

    private static final String BEARER_PREFIX = "Bearer ";

    private final AuthService authService;

    /** POST /auth/login  { "username": "admin", "password": "admin1234" } */
    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody LoginRequest request) {
        return authService.login(request)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> unauthorized("Invalid username or password"));
    }

    /** GET /auth/validate  (Authorization: Bearer {token}) */
    @GetMapping("/validate")
    public ResponseEntity<?> validate(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization) {
        String token = extractToken(authorization);
        if (token == null) {
            return unauthorized("Missing bearer token");
        }
        return authService.validate(token)
                .<ResponseEntity<?>>map(info -> ResponseEntity.ok(Map.of(
                        "valid", true,
                        "username", info.getUsername(),
                        "expiresAt", info.getExpiresAt().toString()
                )))
                .orElseGet(() -> unauthorized("Invalid or expired token"));
    }

    /** POST /auth/logout  (Authorization: Bearer {token}) */
    @PostMapping("/logout")
    public ResponseEntity<?> logout(@RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization) {
        String token = extractToken(authorization);
        if (token == null || !authService.logout(token)) {
            return unauthorized("Invalid or expired token");
        }
        return ResponseEntity.ok(Map.of("message", "Logged out"));
    }

    private String extractToken(String authorization) {
        if (authorization == null || !authorization.startsWith(BEARER_PREFIX)) {
            return null;
        }
        return authorization.substring(BEARER_PREFIX.length()).trim();
    }

    private ResponseEntity<?> unauthorized(String message) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(Map.of("message", message));
    }
}
