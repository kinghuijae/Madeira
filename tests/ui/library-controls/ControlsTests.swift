import XCTest

final class ControlsTests: XCTestCase {
    func testProductionControls() { check([]) }

    private func check(_ arguments: [String]) {
        continueAfterFailure = true
        let app = XCUIApplication()
        app.launchArguments = arguments
        var exercisedVerticalBar = false
        for orientation in [UIDeviceOrientation.portrait] {
            XCUIDevice.shared.orientation = orientation
            app.launch()
            XCTAssertTrue(app.buttons["add"].waitForExistence(timeout: 20))
            let add = app.buttons["add"]
            let settings = app.buttons["Settings"]
            let screen = app.windows.firstMatch.frame
            let isVertical = abs(add.frame.midX - settings.frame.midX) < 80
                && (add.frame.midX > screen.maxX - 100 || add.frame.midX < screen.minX + 100)
            exercisedVerticalBar = exercisedVerticalBar || isVertical
            print("CONTROLS variant=\(arguments) orientation=\(orientation.rawValue) vertical=\(isVertical) add=\(add.frame) settings=\(settings.frame)")
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.lifetime = .keepAlways
            self.add(screenshot)
            add.tap()
            XCTAssertTrue(app.staticTexts["add-sheet"].waitForExistence(timeout: 3), "Add must present its sheet")
            app.terminate()
            app.launch()
            XCTAssertTrue(app.buttons["sort"].waitForExistence(timeout: 10))
            app.buttons["sort"].tap()
            let sort = app.buttons["Sort games"]
            XCTAssertTrue(sort.waitForExistence(timeout: 3), "Sort menu must open")
            if sort.exists { sort.tap() }
            XCTAssertEqual(app.staticTexts["games"].label, "Sorted games")
            app.buttons["Settings"].tap()
            XCTAssertTrue(app.staticTexts["settings-page"].waitForExistence(timeout: 3), "Settings tab must open")
            app.buttons["Library"].tap()
            XCTAssertTrue(app.staticTexts["games"].waitForExistence(timeout: 3), "Library tab must open")
            print(app.debugDescription)
            app.terminate()
        }
        if arguments.contains("--horizontal-bars") {
            XCTAssertFalse(exercisedVerticalBar, "Horizontal fallback must cover the toolbar and tab bar")
        } else {
            XCTAssertTrue(exercisedVerticalBar, "Test must run in a Duo pose with a vertical bar")
        }
    }
}
