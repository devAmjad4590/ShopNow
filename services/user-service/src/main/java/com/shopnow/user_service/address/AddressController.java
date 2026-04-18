package com.shopnow.user_service.address;

import com.shopnow.user_service.config.AuthUserId;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/users/me/addresses")
public class AddressController {

    private final AddressService addressService;

    @GetMapping
    public ResponseEntity<List<AddressResponse>> list(@AuthUserId Integer userId) {
        return ResponseEntity.ok(addressService.listAddresses(userId));
    }

    @PostMapping
    public ResponseEntity<AddressResponse> create(
            @AuthUserId Integer userId,
            @RequestBody @Valid AddressRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(addressService.createAddress(userId, req));
    }

    @PutMapping("/{id}")
    public ResponseEntity<AddressResponse> update(
            @AuthUserId Integer userId,
            @PathVariable Integer id,
            @RequestBody @Valid AddressRequest req) {
        return ResponseEntity.ok(addressService.updateAddress(userId, id, req));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@AuthUserId Integer userId, @PathVariable Integer id) {
        addressService.deleteAddress(userId, id);
        return ResponseEntity.noContent().build();
    }
}
