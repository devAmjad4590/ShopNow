package com.shopnow.user_service.admin;

import com.shopnow.user_service.config.AuthRole;
import com.shopnow.user_service.profile.ProfileResponse;
import com.shopnow.user_service.profile.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequiredArgsConstructor
@RequestMapping("/users")
public class AdminUserController {

    private final UserProfileService profileService;

    @GetMapping("/{id}")
    public ResponseEntity<ProfileResponse> getById(@PathVariable Integer id, @AuthRole String role) {
        if (!"ADMIN".equals(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Admin access required");
        }
        return ResponseEntity.ok(profileService.getProfileById(id));
    }
}
