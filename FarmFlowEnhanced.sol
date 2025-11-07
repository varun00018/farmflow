// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract FarmFlowEnhanced {

    struct Crop {
        string name;
        uint256 basePricePerKg;
        uint256 currentPricePerKg;
        uint256 stock;
        address farmer;
        string imageHash;  // IPFS hash
        string location;   // lat,long
        uint256 alphaScore; // DCRI score (scaled by 1000, e.g., 0.5 = 500)
        uint256 lastPriceUpdate;
        bool active;
    }

    struct Purchase {
        string cropName;
        uint256 qty;
        uint256 totalPrice;
        address buyer;
        address farmer;
        uint256 timestamp;
    }

    struct InsurancePolicy {
        uint256 premiumPaid;
        uint256 coverageAmount;
        uint256 purchaseDate;
        bool active;
    }

    struct InsuranceClaim {
        uint256 claimId;
        address farmer;
        uint256 cropId;
        uint256 claimAmount;
        string reason;
        string evidenceHash; // IPFS hash
        uint256 timestamp;
        ClaimStatus status;
    }

    enum ClaimStatus { Pending, Approved, Rejected }

    // State variables
    mapping(uint256 => Crop) public crops;
    uint256 public cropCount;

    mapping(address => uint256) public buyerBalance;
    mapping(address => uint256) public farmerBalance;
    mapping(address => uint256) public insuranceBalance;

    mapping(address => Purchase[]) public buyerPurchases;
    mapping(address => Purchase[]) public farmerSales;

    mapping(address => InsurancePolicy) public insurancePolicies;
    mapping(uint256 => InsuranceClaim) public insuranceClaims;
    uint256 public claimCount;

    address public insuranceAuthority;
    uint256 public constant INSURANCE_PREMIUM = 100; // 100 coins
    uint256 public constant COVERAGE_MULTIPLIER = 10; // 10x coverage

    // Events
    event CropAdded(uint256 cropId, string name, uint256 pricePerKg, uint256 stock, address farmer);
    event CropUpdated(uint256 cropId, uint256 newStock, uint256 newPrice);
    event CropPriceUpdatedByDCRI(uint256 cropId, uint256 oldPrice, uint256 newPrice, uint256 alphaScore);
    event Bought(address buyer, address farmer, uint256 cropId, uint256 qty, uint256 totalPrice);
    event InsurancePurchased(address farmer, uint256 premium, uint256 coverage);
    event ClaimSubmitted(uint256 claimId, address farmer, uint256 cropId, uint256 amount);
    event ClaimProcessed(uint256 claimId, ClaimStatus status, uint256 payoutAmount);

    constructor() {
        insuranceAuthority = msg.sender;
        
        // Preload initial crops
        addCrop("Apple", 180, 5, "QmDefault1", "0,0");
        addCrop("Tomato", 100, 25, "QmDefault2", "0,0");
        addCrop("Potato", 100, 20, "QmDefault3", "0,0");
    }

    modifier onlyInsuranceAuthority() {
        require(msg.sender == insuranceAuthority, "Only insurance authority");
        _;
    }

    // =============== Farmer Functions ===============

    function addCrop(
        string memory name, 
        uint256 pricePerKg, 
        uint256 stock,
        string memory imageHash,
        string memory location
    ) public {
        cropCount++;
        crops[cropCount] = Crop({
            name: name,
            basePricePerKg: pricePerKg,
            currentPricePerKg: pricePerKg,
            stock: stock,
            farmer: msg.sender,
            imageHash: imageHash,
            location: location,
            alphaScore: 0,
            lastPriceUpdate: block.timestamp,
            active: true
        });
        emit CropAdded(cropCount, name, pricePerKg, stock, msg.sender);
    }

    function updateCropDCRI(uint256 cropId, uint256 alphaScore) public {
        //require(crops[cropId].farmer == msg.sender, "Not your crop");
        //require(alphaScore <= 1000, "Invalid alpha score");
        
        Crop storage crop = crops[cropId];
        uint256 oldPrice = crop.currentPricePerKg;
        
        crop.alphaScore = alphaScore;
        
        // Update price based on alpha (risk score)
        // Lower risk = higher price, Higher risk = lower price
        // Formula: newPrice = basePrice * (1 + (1 - alpha) * 0.5)
        // If alpha = 0 (no risk): price increases by 50%
        // If alpha = 1 (high risk): price stays at base
        uint256 priceMultiplier = 1000 + ((1000 - alphaScore) * 500 / 1000);
        crop.currentPricePerKg = (crop.basePricePerKg * priceMultiplier) / 1000;
        crop.lastPriceUpdate = block.timestamp;
        
        emit CropPriceUpdatedByDCRI(cropId, oldPrice, crop.currentPricePerKg, alphaScore);
    }

    function addStock(uint256 cropId, uint256 amount) public {
        require(crops[cropId].farmer == msg.sender, "Not your crop");
        crops[cropId].stock += amount;
        emit CropUpdated(cropId, crops[cropId].stock, crops[cropId].currentPricePerKg);
    }

    function getCropCount() public view returns (uint256) {
        return cropCount;
    }

    function changePrice(uint256 cropId, uint256 newPrice) public {
        require(crops[cropId].farmer == msg.sender, "Not your crop");
        crops[cropId].basePricePerKg = newPrice;
        crops[cropId].currentPricePerKg = newPrice;
        emit CropUpdated(cropId, crops[cropId].stock, newPrice);
    }

    function deactivateCrop(uint256 cropId) public {
        require(crops[cropId].farmer == msg.sender, "Not your crop");
        crops[cropId].active = false;
    }

    function getFarmerBalance(address farmer) public view returns (uint256) {
        return farmerBalance[farmer];
    }

    function getFarmerSales(address farmer) public view returns (Purchase[] memory) {
        return farmerSales[farmer];
    }

    function withdrawFarmerBalance(uint256 amount) public {
        require(farmerBalance[msg.sender] >= amount, "Insufficient balance");
        farmerBalance[msg.sender] -= amount;
        // In real implementation, transfer actual tokens/ETH
    }

    // =============== Buyer Functions ===============

    function topUpBalance(uint256 amount) public {
        buyerBalance[msg.sender] += amount;
    }

    function buyCrop(uint256 cropId, uint256 qty) public {
        Crop storage crop = crops[cropId];
        require(crop.active, "Crop not available");
        
        uint256 totalPrice = crop.currentPricePerKg * qty;

        require(buyerBalance[msg.sender] >= totalPrice, "Not enough balance");
        require(crop.stock >= qty, "Not enough stock");

        buyerBalance[msg.sender] -= totalPrice;
        farmerBalance[crop.farmer] += totalPrice;
        crop.stock -= qty;

        Purchase memory p = Purchase(
            crop.name, 
            qty, 
            totalPrice, 
            msg.sender, 
            crop.farmer, 
            block.timestamp
        );
        buyerPurchases[msg.sender].push(p);
        farmerSales[crop.farmer].push(p);

        emit Bought(msg.sender, crop.farmer, cropId, qty, totalPrice);
    }

    function getBuyerBalance(address buyer) public view returns (uint256) {
        return buyerBalance[buyer];
    }

    function getBuyerPurchases(address buyer) public view returns (Purchase[] memory) {
        return buyerPurchases[buyer];
    }

    // =============== Insurance Functions ===============

    function purchaseInsurance() public {
        require(farmerBalance[msg.sender] >= INSURANCE_PREMIUM, "Insufficient balance");
        require(!insurancePolicies[msg.sender].active, "Already insured");

        farmerBalance[msg.sender] -= INSURANCE_PREMIUM;
        insuranceBalance[insuranceAuthority] += INSURANCE_PREMIUM;

        uint256 coverage = INSURANCE_PREMIUM * COVERAGE_MULTIPLIER;
        insurancePolicies[msg.sender] = InsurancePolicy({
            premiumPaid: INSURANCE_PREMIUM,
            coverageAmount: coverage,
            purchaseDate: block.timestamp,
            active: true
        });

        emit InsurancePurchased(msg.sender, INSURANCE_PREMIUM, coverage);
    }

    function submitClaim(
        uint256 cropId, 
        uint256 claimAmount, 
        string memory reason,
        string memory evidenceHash
    ) public {
        require(insurancePolicies[msg.sender].active, "No active insurance");
        require(crops[cropId].farmer == msg.sender, "Not your crop");
        require(claimAmount <= insurancePolicies[msg.sender].coverageAmount, "Exceeds coverage");

        claimCount++;
        insuranceClaims[claimCount] = InsuranceClaim({
            claimId: claimCount,
            farmer: msg.sender,
            cropId: cropId,
            claimAmount: claimAmount,
            reason: reason,
            evidenceHash: evidenceHash,
            timestamp: block.timestamp,
            status: ClaimStatus.Pending
        });

        emit ClaimSubmitted(claimCount, msg.sender, cropId, claimAmount);
    }

    function processClaim(uint256 claimId, bool approve) public onlyInsuranceAuthority {
        InsuranceClaim storage claim = insuranceClaims[claimId];
        require(claim.status == ClaimStatus.Pending, "Claim already processed");

        uint256 payout = 0;
        if (approve) {
            claim.status = ClaimStatus.Approved;
            payout = claim.claimAmount;
            
            require(insuranceBalance[insuranceAuthority] >= payout, "Insufficient insurance funds");
            insuranceBalance[insuranceAuthority] -= payout;
            farmerBalance[claim.farmer] += payout;
            
            // Deactivate insurance after claim
            insurancePolicies[claim.farmer].active = false;
        } else {
            claim.status = ClaimStatus.Rejected;
        }

        emit ClaimProcessed(claimId, claim.status, payout);
    }

    function getInsurancePolicy(address farmer) public view returns (InsurancePolicy memory) {
        return insurancePolicies[farmer];
    }

    function getPendingClaims() public view returns (InsuranceClaim[] memory) {
        uint256 pendingCount = 0;
        for (uint256 i = 1; i <= claimCount; i++) {
            if (insuranceClaims[i].status == ClaimStatus.Pending) {
                pendingCount++;
            }
        }

        InsuranceClaim[] memory pending = new InsuranceClaim[](pendingCount);
        uint256 index = 0;
        for (uint256 i = 1; i <= claimCount; i++) {
            if (insuranceClaims[i].status == ClaimStatus.Pending) {
                pending[index] = insuranceClaims[i];
                index++;
            }
        }
        return pending;
    }

    function getFarmerClaims(address farmer) public view returns (InsuranceClaim[] memory) {
        uint256 farmerClaimCount = 0;
        for (uint256 i = 1; i <= claimCount; i++) {
            if (insuranceClaims[i].farmer == farmer) {
                farmerClaimCount++;
            }
        }

        InsuranceClaim[] memory claims = new InsuranceClaim[](farmerClaimCount);
        uint256 index = 0;
        for (uint256 i = 1; i <= claimCount; i++) {
            if (insuranceClaims[i].farmer == farmer) {
                claims[index] = insuranceClaims[i];
                index++;
            }
        }
        return claims;
    }

    // =============== View Functions ===============

    function getAllCrops() public view returns (Crop[] memory) {
        Crop[] memory allCrops = new Crop[](cropCount);
        for (uint256 i = 1; i <= cropCount; i++) {
            allCrops[i-1] = crops[i];
        }
        return allCrops;
    }

    function getAvailableCrops() public view returns (Crop[] memory) {
        uint256 availableCount = 0;
        for (uint256 i = 1; i <= cropCount; i++) {
            if (crops[i].stock > 0 && crops[i].active) availableCount++;
        }

        Crop[] memory available = new Crop[](availableCount);
        uint256 j = 0;
        for (uint256 i = 1; i <= cropCount; i++) {
            if (crops[i].stock > 0 && crops[i].active) {
                available[j] = crops[i];
                j++;
            }
        }
        return available;
    }

    function getCrop(uint256 cropId) public view returns (Crop memory) {
        return crops[cropId];
    }

    function getInsuranceAuthority() public view returns (address) {
        return insuranceAuthority;
    }
}