package com.shopnow.auth_service.internal;

import com.shopnow.auth_service.user.User;
import com.shopnow.auth_service.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/internal/users")
public class InternalAuthController {

    private final UserRepository userRepository;

    @GetMapping("/{id}")
    public ResponseEntity<UserInfoResponse> getById(@PathVariable Integer id) {
        return userRepository.findById(id)
                .map(u -> ResponseEntity.ok(new UserInfoResponse(u.getId(), u.getEmail(), u.getFirstName(), u.getLastName())))
                .orElse(ResponseEntity.notFound().build());
    }
}
