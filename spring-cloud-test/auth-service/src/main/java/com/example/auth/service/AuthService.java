package com.example.auth.service;

import com.example.auth.dto.LoginRequest;
import com.example.auth.dto.LoginResponse;
import com.example.auth.dto.TokenInfo;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

/**
 * 외부 DB 없이 메모리에서 사용자/토큰을 관리하는 테스트용 인증 서비스.
 */
@Slf4j
@Service
public class AuthService {

    private static final Duration TOKEN_TTL = Duration.ofHours(1);
    private static final String TOKEN_TYPE = "Bearer";

    // 테스트 계정 (username -> password)
    private final Map<String, String> users = Map.of(
            "admin", "admin1234",
            "user", "user1234"
    );

    private final Map<String, TokenInfo> tokens = new ConcurrentHashMap<>();

    public Optional<LoginResponse> login(LoginRequest request) {
        if (request == null || request.getUsername() == null || request.getPassword() == null) {
            return Optional.empty();
        }

        String savedPassword = users.get(request.getUsername());
        if (savedPassword == null || !savedPassword.equals(request.getPassword())) {
            log.info("login failed: {}", request.getUsername());
            return Optional.empty();
        }

        Instant now = Instant.now();
        String token = UUID.randomUUID().toString();
        tokens.put(token, TokenInfo.builder()
                .username(request.getUsername())
                .issuedAt(now)
                .expiresAt(now.plus(TOKEN_TTL))
                .build());

        log.info("login success: {}", request.getUsername());
        return Optional.of(LoginResponse.builder()
                .accessToken(token)
                .tokenType(TOKEN_TYPE)
                .expiresIn(TOKEN_TTL.toSeconds())
                .username(request.getUsername())
                .build());
    }

    public Optional<TokenInfo> validate(String token) {
        TokenInfo info = tokens.get(token);
        if (info == null) {
            return Optional.empty();
        }
        if (info.isExpired()) {
            tokens.remove(token);
            return Optional.empty();
        }
        return Optional.of(info);
    }

    public boolean logout(String token) {
        return tokens.remove(token) != null;
    }
}
