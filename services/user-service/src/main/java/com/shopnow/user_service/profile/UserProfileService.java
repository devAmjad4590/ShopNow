package com.shopnow.user_service.profile;

import com.shopnow.user_service.exception.ProfileNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class UserProfileService {

    private final UserProfileRepository profileRepository;

    public ProfileResponse getProfile(Integer authUserId) {
        UserProfile profile = profileRepository.findByAuthUserId(authUserId)
                .orElseGet(() -> createEmptyProfile(authUserId));
        return toResponse(profile);
    }

    public ProfileResponse updateProfile(Integer authUserId, ProfileUpdateRequest req) {
        UserProfile profile = profileRepository.findByAuthUserId(authUserId)
                .orElseGet(() -> UserProfile.builder().authUserId(authUserId).build());

        profile.setPhone(req.getPhone());
        profile.setDateOfBirth(req.getDateOfBirth());
        profile.setAvatarUrl(req.getAvatarUrl());
        profile.setBio(req.getBio());

        return toResponse(profileRepository.save(profile));
    }

    public ProfileResponse getProfileById(Integer authUserId) {
        UserProfile profile = profileRepository.findByAuthUserId(authUserId)
                .orElseThrow(() -> new ProfileNotFoundException("Profile not found for user " + authUserId));
        return toResponse(profile);
    }

    private UserProfile createEmptyProfile(Integer authUserId) {
        return profileRepository.save(UserProfile.builder().authUserId(authUserId).build());
    }

    private ProfileResponse toResponse(UserProfile p) {
        return ProfileResponse.builder()
                .authUserId(p.getAuthUserId())
                .phone(p.getPhone())
                .dateOfBirth(p.getDateOfBirth())
                .avatarUrl(p.getAvatarUrl())
                .bio(p.getBio())
                .build();
    }
}
