# OpenStudio EE Measures 

EE measures used by OpenStudio. This contains general use energy efficiency measures. Some measures here may also be suitable for calibration or model articulation. Similarly, some measures in other measure gem repos may also be suitable for energy efficiency usage.


## Installation

Add this line to your application's Gemfile:

```ruby
gem 'openstudio-ee-measures'
```

And then execute:

    $ bundle

Or install it yourself as:

    $ gem install 'openstudio-ee-measures'

## Usage

To be filled out later.

## TODO

- [x] Remove measures from OpenStudio-Measures to standardize on this location

# Releasing

* Update CHANGELOG.md
* Run `rake rubocop:auto_correct`
* Update version in `/lib/openstudio/ee_measures/version.rb`
* Create PR to master, after tests and reviews complete, then merge
* Locally - from the master branch, run `rake release`
* On GitHub, go to the releases page and update the latest release tag. Name it �Version x.y.z� and copy the CHANGELOG entry into the description box.

