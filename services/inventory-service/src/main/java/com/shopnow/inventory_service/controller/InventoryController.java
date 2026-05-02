package com.shopnow.inventory_service.controller;

import com.shopnow.inventory_service.dto.InventoryResponse;
import com.shopnow.inventory_service.dto.StockSeedRequest;
import com.shopnow.inventory_service.dto.StockUpdateRequest;
import com.shopnow.inventory_service.service.InventoryService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

// Demo flow: POST /seed with productId first, then POST /api/v1/orders to place an order.
@RestController
@RequestMapping("/inventory")
@RequiredArgsConstructor
public class InventoryController {

    private final InventoryService inventoryService;

    @PostMapping("/seed")
    public ResponseEntity<InventoryResponse> seed(@Valid @RequestBody StockSeedRequest request) {
        return ResponseEntity.ok(InventoryService.toResponse(
                inventoryService.seedStock(request.productId(), request.productName(), request.quantity())));
    }

    @GetMapping("/{productId}")
    public ResponseEntity<InventoryResponse> getStock(@PathVariable Long productId) {
        return ResponseEntity.ok(InventoryService.toResponse(inventoryService.getStock(productId)));
    }

    @GetMapping
    public ResponseEntity<List<InventoryResponse>> getAllStock() {
        return ResponseEntity.ok(inventoryService.getAllStock().stream()
                .map(InventoryService::toResponse)
                .toList());
    }

    @PutMapping("/{productId}/adjust")
    public ResponseEntity<InventoryResponse> adjustStock(
            @PathVariable Long productId,
            @Valid @RequestBody StockUpdateRequest request) {
        return ResponseEntity.ok(InventoryService.toResponse(
                inventoryService.adjustStock(productId, request.quantityDelta())));
    }
}
