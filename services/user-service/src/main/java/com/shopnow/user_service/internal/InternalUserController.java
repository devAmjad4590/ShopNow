package com.shopnow.user_service.internal;

import com.shopnow.user_service.profile.ProfileResponse;
import com.shopnow.user_service.profile.UserProfileService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/internal/users")
public class InternalUserController {

    private final UserProfileService profileService;

    @GetMapping("/{id}")
    public ResponseEntity<ProfileResponse> getById(@PathVariable Integer id) {
        return ResponseEntity.ok(profileService.getProfileById(id));
    }
}
