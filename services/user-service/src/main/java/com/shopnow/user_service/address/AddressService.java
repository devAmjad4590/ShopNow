package com.shopnow.user_service.address;

import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

@Service
@RequiredArgsConstructor
public class AddressService {

    private final AddressRepository addressRepository;

    public List<AddressResponse> listAddresses(Integer authUserId) {
        return addressRepository.findAllByAuthUserId(authUserId)
                .stream().map(this::toResponse).toList();
    }

    public AddressResponse createAddress(Integer authUserId, AddressRequest req) {
        Address address = Address.builder()
                .authUserId(authUserId)
                .label(req.getLabel())
                .line1(req.getLine1())
                .line2(req.getLine2())
                .city(req.getCity())
                .state(req.getState())
                .country(req.getCountry())
                .postalCode(req.getPostalCode())
                .isDefault(req.isDefault())
                .build();
        return toResponse(addressRepository.save(address));
    }

    public AddressResponse updateAddress(Integer authUserId, Integer addressId, AddressRequest req) {
        Address address = addressRepository.findByIdAndAuthUserId(addressId, authUserId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Address not found"));

        address.setLabel(req.getLabel());
        address.setLine1(req.getLine1());
        address.setLine2(req.getLine2());
        address.setCity(req.getCity());
        address.setState(req.getState());
        address.setCountry(req.getCountry());
        address.setPostalCode(req.getPostalCode());
        address.setDefault(req.isDefault());

        return toResponse(addressRepository.save(address));
    }

    public void deleteAddress(Integer authUserId, Integer addressId) {
        Address address = addressRepository.findByIdAndAuthUserId(addressId, authUserId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Address not found"));
        addressRepository.delete(address);
    }

    private AddressResponse toResponse(Address a) {
        return AddressResponse.builder()
                .id(a.getId())
                .label(a.getLabel())
                .line1(a.getLine1())
                .line2(a.getLine2())
                .city(a.getCity())
                .state(a.getState())
                .country(a.getCountry())
                .postalCode(a.getPostalCode())
                .isDefault(a.isDefault())
                .build();
    }
}
