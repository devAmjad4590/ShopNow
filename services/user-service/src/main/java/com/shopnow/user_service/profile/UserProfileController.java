package com.shopnow.user_service.profile;

import com.shopnow.user_service.config.AuthUserId;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/users/me/profile")
public class UserProfileController {

    private final UserProfileService profileService;

    @GetMapping
    public ResponseEntity<ProfileResponse> getMyProfile(@AuthUserId Integer userId) {
        return ResponseEntity.ok(profileService.getProfile(userId));
    }

    @PutMapping
    public ResponseEntity<ProfileResponse> updateMyProfile(
            @AuthUserId Integer userId,
            @RequestBody @Valid ProfileUpdateRequest req) {
        return ResponseEntity.ok(profileService.updateProfile(userId, req));
    }
}
